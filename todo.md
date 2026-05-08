# a2kit — v0.11+ todo

Captured from contract / asyncio / OTel audit (2026-05-08, post v0.10.0).

Priority order for this turn: **types & consumer API first**, then async, then OTel.

---

## P0 — public API / vocabulary  ✅ DONE (v0.11.0.dev0)

- [x] Moved `ConnectionInfoLike` / `ConnectionStoreLike` → `connections.py` (re-exported from `errors.py` shim).
- [x] Renamed `a2kit.errors` → `a2kit.enrichers`; `a2kit.errors` is now a `DeprecationWarning` shim (removed in v0.13).
- [x] Dropped `A2KIT_CONFIG_HOME` self-alias; raises `ImportError` with hint pointing to `ENV_CONFIG_HOME`.
- [x] Replaced `Any` on `Router.store / .enricher / .resolver_registry / .ephemeral`. `ephemeral` uses `Mapping` (covariant) for subclass compat.
- [x] Added `FastMCPLike` Protocol in `scaffold.py`; `MCPRunner(server: FastMCPLike, store: ConnectionStore[Any] | None)`.
- [x] Tightened `RouterRegistry._routers` with `_RouterEntry` NamedTuple. Internal `_RegisterableRouter` Protocol documents the duck-typed shape.
- [x] Public `tool_metadata(fn) → ToolMetadata` (frozen, slotted dataclass) wraps the `_a2kit_*` stamps. Exported from top-level `a2kit`.
- [x] Locked `Page[T]` `next_cursor` opaque-str contract in docstring. Left `T` unbounded (Pydantic v2 bound interplay was fragile).
- [x] Hide internal re-exports — reviewed; `BudgetConfig`/`RunnerConfig` are legitimate consumer surface (pyproject [tool.a2kit.runner] config), kept.

Bonus:
- [x] Tightened `ConnectionStoreLike.list_connections() → Sequence[ConnectionInfoLike]` (covariant) so concrete `list[WidgetConn]` returns satisfy the Protocol.
- [x] CHANGELOG entry, README link table updated, version bumped to `0.11.0.dev0`.
- [x] 12 new tests in `test_v11.py`. 618 tests, 100% coverage, ruff + ty clean.

## P1 — formatter robustness

- [ ] **Fix `format_from_annotation` decision-tree gaps** (`formatter.py:128-167`):
  - Bare `dict`, `Mapping[...]`, `TypedDict` → return `"json"`.
  - Unwrap `Awaitable[T]` / `Coroutine[..., T]` before classifying — async tools currently lose precomputation.
- [ ] **`Page[Union[A, B]]`** falls to runtime silently. Add test + log.
- [ ] **`_dump_items` silently drops non-dict/non-BaseModel** (`formatter.py:186-198`).
  - `[1, 2, 3]` → `[]`. Raise instead.
- [ ] **`_flat_pydantic_fields` Union-stripping** handles `Optional[T]` only with one non-None arm. `Optional[Union[A, B]]` falls through.
- [ ] **Drop runtime `_is_uniform_row_list` cross-check** when `_a2kit_format` is set. Trust decoration; let tool bugs surface.

## P1 — verification (Hypothesis)

- [ ] **Property test**: `format_from_annotation(T)` precompute ↔ `toon_or_json(model_dump(instance))` runtime agree for any Pydantic model.
- [ ] **Property test**: `truncate(x)` is structural identity except str clipping; never mutates input.
- [ ] **Property test**: `_coerce_key` accepts {kwargs, tuple, list, NamedTuple, single-string-when-arity-1}; rejects everything else with typed error.

## P2 — asyncio-first

- [ ] **Async connection-store API** (`connections.py:288-315`)
  - Add `load_async`, `save_async`, `list_connections_async` via `anyio.to_thread.run_sync`.
  - Keep sync API intact (sync tools still work).
- [ ] **Switch `_lookup_connection`** (`tools.py:202-208`) to await async variant from `async_wrapper`.
- [ ] **`MCPRunner.run_async()`** for embedding into existing event loop.
- [ ] **`_TRANSPORT_LOCAL` → ContextVar** (`tools.py:81-92`) for consistency with `_RouterContext`.
- [ ] **`EnricherFn` accepts async**: `Callable[..., Exception | Awaitable[Exception]]`. Lets enrichers do async lookups (SSO, etc.).

## P2 — OTel / observability

- [ ] **Record exceptions on the span** — biggest hole. Move `except Exception as exc:` (`tools.py:580, 619`) inside `with span_cm:`, call `span.record_exception(exc)` + `set_status(ERROR)` before enricher runs.
- [ ] **`a2kit.get_tool_logger(name)`** — `LoggerAdapter` injecting `tool.name` + `connection.key`. Auto-correlates with span under OTel `LoggingInstrumentor`.
- [ ] **`tool.result.count` span attribute** when result is list/`Page` (cardinality only — PII safe).
- [ ] **Provider-class string check is fragile** (`_otel.py:64`). Use `isinstance(provider, trace.ProxyTracerProvider)` with `ImportError` fallback.
- [ ] **Spike**: does FastMCP expose MCP JSON-RPC request ID? If yes, stamp as `mcp.request_id` span attribute.

## P3 — internal cleanup (deferred from review)

- [ ] Move `_check_tool_call_contamination` str-typed param set to decoration time (`tools.py:541-544`).
- [ ] `_auto_inject_enabled` cache → `functools.cache`-wrapped fn (`tools.py:790`).
- [ ] `_resolve_store(self, fallback)` helper to dedupe 3x two-tier fallback in scaffold.
- [ ] Tighten `Iterable[ConnectionInfoLike]` → `Sequence` on Protocol (or materialize internally).
- [ ] Document `chain(*enrichers)` first-transforms-wins semantics + lock with short-circuit test.
- [ ] Deprecate tuple/list arms of `_resolve_connection_key` (`tools.py:155-164`); v0.12 delete.
- [ ] MAX_DISPLAYED_CONNECTIONS module constant in `docs.py` (was deferred from v0.10 review).
- [ ] Schema-staleness doc note on `connection_enricher` (decoration-time keys).
- [ ] Lint rules A2K001-A2K013 update for v0.10 patterns.

---

## Top 3 v0.11 bets (from audit)

1. Untangle `errors`/`exceptions` vocabulary (P0 first three items).
2. Replace `Any` on `Router` + `MCPRunner` (P0 typing items).
3. Hypothesis suite for `format_from_annotation` ↔ `toon_or_json` agreement.

---

# v0.12 — integration surface redesign

Captured from brainstorm (2026-05-08). Driving principle: **very simple on the
surface for 80% of MCPs, lots enabled OOB *because* of the convention,
FastMCP passthrough preserved**.

## Three verbs

`@a2kit.list` / `@a2kit.read` / `@a2kit.write` (and the same names at
`@MyRouter.list/read/write`). No `_tool` suffix — same word at both levels.
`@a2kit.tool(...)` stays as the explicit-everything escape hatch.

| Verb | Caps | List-view defaults | Notes |
|---|---|---|---|
| `list` | adds `Cap.READ` | `filter=Local, fields=Local, pagination=Local` | many-out, no query in |
| `read` | adds `Cap.READ` | off | single complex query → result |
| `write` | adds `Cap.WRITE` | off | mutation |

Verb-implied caps are non-subtractable. To opt out: use `@a2kit.tool(...)` directly.

## Drop `server=` from the decorator

The runner registers, not the decorator. The decorator only stamps metadata.

```python
# v0.11 (today)
@a2kit.tool(server=server, store=jira_store, write=True, capabilities={Cap.WRITE})
async def close_issue(*, info: JiraConn, issue_id: str) -> Issue: ...

# v0.12
@a2kit.write
async def close_issue(*, jira: JiraConn, issue_id: str) -> Issue: ...
```

Tools are picked up either via:
- **Module-level registry** (auto): `@a2kit.<verb>` records into a thread-local
  registry; `MCPRunner` walks it at startup. Magic but short.
- **Explicit list**: `MCPRunner(server, tools=[close_issue, ...])`. Refactor-safe.

Default to **explicit list**. Auto-registry can be added later if friction is real.

## Drop `store=` from the decorator. Type-driven DI on the runner.

Connection stores live on the runner under a generic `provides=` kwarg (NOT
`stores=` — DI container is the abstraction; stores happen to be one provider type
today, more provider types coming).

```python
runner = MCPRunner(server, provides=[jira_store, conf_store])
# v0.13+: runner = MCPRunner(server, provides=[jira_store, OTelMeter(...), CassetteRouter(...)])
```

At startup the runner builds a **`type → provider`** index. Each provider exposes
its produced type via a `__provides__` attribute (or for `ConnectionStore[T]`,
derived from the parametric type). Anything implementing a `Provider` Protocol fits.

Resolution rules (v0.12):
- One type, one provider. Two providers for the same type → startup `ValueError`.
- Tool annotated with type T but no provider for T → startup `ValueError`.
- Subclass relationships do NOT auto-resolve: tool annotated with `JiraConn`
  while only `ProdJiraConn(JiraConn)` is registered → error. Forces clarity.
- `Annotated[T, "tag"]` is reserved for v0.13+ if real users need same-type tagging.

To run two of the same kind, declare two types:

```python
class ProdJiraConn(JiraConn): ...
class StagingJiraConn(JiraConn): ...

prod_store = ConnectionStore(ProdJiraConn)
staging_store = ConnectionStore(StagingJiraConn)

runner = MCPRunner(server, provides=[prod_store, staging_store])

@a2kit.write
async def close_issue(*, jira: ProdJiraConn, issue_id: str) -> Issue: ...
```

## Drop the `info` naming convention

Type-driven DI dispatches on type, not name. The author chooses the param name.

```python
# v0.11 — convention encouraged `info`
@a2kit.tool(store=jira_store)
async def list_issues(*, info: JiraConn) -> list[Issue]: ...

# v0.12 — pick whatever reads best
@a2kit.list
async def list_issues(*, jira: JiraConn) -> list[Issue]: ...
```

## What stays as `@a2kit.tool(...)`

- Cap subtraction / odd capability shapes.
- Decorator authors who genuinely want `connection=False` (utility tools with
  no DI).
- `tool_call_guard=False`, `otel=False`, `streaming=True`, `tool_name=...`,
  `cli=...`, `enricher=...` — all the rare-but-real overrides.
- Backwards-compat for v0.11 code that doesn't migrate.

The verb decorators are **thin wrappers** that call `tool(...)` with verb
defaults applied. Implementation cost: ~30 SLOC each, plus a thin Router method.

## Connection-as-plugin: deferred to v0.13

The v0.12 user-facing surface already looks plugin-shaped:
- `provides=[...]` is a generic DI container.
- The decorator never references "connection" terminology in its kwargs.
- Type-driven dispatch makes the binding pluggable internally.

v0.13 then becomes: pull the connection-binding logic out of `tools/_decorator.py`
into a `ConnectionPlugin` registered with the runner. **Zero user-facing change.**
Plugins beyond connections (cassette, otel, secret resolvers) get designed once
we have a real second/third candidate to anchor the contract.

## Migration story (v0.11 → v0.12)

1. Replace `@a2kit.tool(server=server, store=X, write=True)` with verb decorator
   (`@a2kit.write`).
2. Move `store=X` declarations from per-tool kwargs to `MCPRunner(provides=[X])`.
3. Rename `info: JiraConn` to whatever reads best (or leave `info` — it works,
   just no longer special).
4. v0.11's full kwarg surface keeps working — `@a2kit.tool(...)` is the escape
   hatch. Only verb-syntax adopters migrate.

A2K-series lint additions for v0.12:
- A2K015 — `@a2kit.tool(server=...)` flagged; suggest dropping + using `provides=`.
- A2K016 — `@a2kit.tool(store=...)` flagged; suggest moving to `provides=`.
- Extend `is_a2kit_tool_decorator` to recognise `list`/`read`/`write` for all
  existing rules.

## v0.12 implementation order

1. Top-level `@a2kit.list/read/write` as wrappers around `tool(...)`.
2. `@MyRouter.list` (joins existing `.read`/`.write`).
3. `MCPRunner.provides=` — register stores, build type index at startup.
4. Refactor `_lookup_connection_*` to consult the runner's type index.
5. Lint additions (A2K015 / A2K016).
6. Bump to `0.12.0.dev0`. CHANGELOG. README rewrite (the surface story is now
   short enough to be the README intro).

Open questions to resolve during implementation:
- Does the runner also accept v0.11-style `store=` for backward compat in the
  same release? Probably yes — one version of overlap eases migration.
- `provides=` vs runner exposing `runner.provides.add(...)` for late binding.
  Default to construction-time list; add late-binding only if a use case appears.

---

## v0.12 — research outcomes (2026-05-08)

Three parallel research agents validated the design choices.

### Hand-roll the DI container (~150 LOC)

Evaluated `dependency-injector`, `lagom`, `punq`, `wired`, `kink`,
`fastapi.Depends`. **None fit** the "look simple" + `provides=[...]` + async +
plugin-carries-CLI surface without a 60–80 LOC wrapper. Hand-roll is ~120 LOC
core + ~30 LOC tests. The wrapper for any library is 50–80 LOC, so net cost of
hand-rolling is ~40 LOC for: zero external dep, no `Provide[]` markers leaking
into tool signatures, debugger steps into our own code.

Sketch (canonical for v0.12):

```python
# a2kit/di.py
@runtime_checkable
class Provider(Protocol):
    """Produces values of self.provides for injection."""
    provides: type
    async def get(self, **ctx: Any) -> Any: ...

class Plugin(Protocol):
    """Runner extension. All members optional except `name`."""
    name: str
    providers: list[Provider]
    commands: list[click.Command]
    async def on_startup(self, runner: MCPRunner) -> None: ...
    async def on_shutdown(self, runner: MCPRunner) -> None: ...

class PluginBase:
    """Convenience base — set `name`, add what you need, defaults are no-ops."""
    providers: list[Provider] = []
    commands: list[click.Command] = []
    async def on_startup(self, runner): pass
    async def on_shutdown(self, runner): pass

@dataclass
class ToolPlan:
    fn: Any
    bindings: list[tuple[str, Provider]]   # (param_name, provider)
    passthrough: list[str]                 # params from MCP client, not injected
```

Author's view (the bar):
```python
class JiraStoreProvider:
    provides = JiraConn
    async def get(self, key: tuple[str, ...] = ("default",)) -> JiraConn:
        return await load_from_disk(key)

class ConnectionPlugin(PluginBase):
    name = "connections"
    providers = [JiraStoreProvider(), ConfStoreProvider()]
    commands = [conn_login, conn_list, conn_rm]   # click commands

runner = MCPRunner(
    server,
    provides=[JiraStoreProvider()],          # bare providers, or
    plugins=[ConnectionPlugin()],             # bundled providers + CLI
)
```

### IMPORTANT — defer compile to startup, not __init__

The research-agent sketch compiles tool plans in `MCPRunner.__init__`. **That's
wrong** — `@a2kit.list/read/write` decorators fire AFTER runner construction,
populating the registry that the runner then walks. Compile must happen at
`MCPRunner._prepare()` time (the existing pre-run step), not in `__init__`.
~10-line difference but easy to miss.

### Click — replace `_parse_multistore_register`

Custom `click.ParamType` with `multiple=True`:

```python
class RegisterBlock(click.ParamType):
    name = "register"
    def convert(self, value, param, ctx):
        head, *kvs = shlex.split(value)
        router, key = head.rstrip(":").split(":", 1)
        return router, key, dict(s.split("=", 1) for s in kvs)

@click.option("--register", "registers", multiple=True, type=RegisterBlock())
```

UX: `--register "jira:prod url=https://x token=t"` (quoted block per call).
Trade-off vs current walker: requires quotes, gains typed errors + `--help`
type name + reusability across plugins. Worth it.

### Click — plugin CLI registration

Manual `cli.add_command(cmd)` from a host-held plugin registry. Plugins
expose `commands: list[click.Command]` (per the Plugin Protocol above); the
runner aggregates at CLI build time. **Reject** `click-plugins`/entry-points
for the core path — they can't pass runtime context (constructed stores) into
commands without globals. Add an entry-points discovery layer LATER if/when
third-party plugins materialise.

### OTel — exception recording

`opentelemetry.trace.Tracer.start_as_current_span` already auto-records
exceptions and sets ERROR status by default (`record_exception=True,
set_status_on_exception=True`). Our manual try/except is partially redundant
*unless* we want a description string and `escaped=True` semantics — which we
do, for richer traces.

Canonical v0.12 pattern:

```python
with span_cm as span:
    try:
        result = await fn(*args, **kwargs)
    except Exception as exc:
        span.record_exception(exc, escaped=True)
        span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
        raise
    if isinstance(result, (list, Page)):
        span.set_attribute("tool.result.count", len(result))
    return result
```

Notes:
- `_NullSpan` grows no-op `record_exception` / `set_status` / `set_attribute`
  methods (matches OTel's own `NonRecordingSpan` shape — no per-call branching
  on `if otel:`).
- `tool.result.count` set after success only — meaningless on error.
- Re-raise inside `with` is safe; span CM ends via `__exit__` regardless.

### Plugin OTel spans — interconnected via OTel context propagation

Plugins emit their own spans nested under the tool's outer span. **No
custom infrastructure needed** — OTel's `start_as_current_span` propagates
context automatically. When the @tool wrapper opens
`a2kit.tool.close_issue` as the *current* span, any
`tracer.start_as_current_span("a2kit.plugin.connections.load")` inside a
provider becomes a child.

Resulting hierarchy:
```
a2kit.tool.close_issue
├── a2kit.plugin.connections.load (key=prod)
├── (tool body executes)
└── a2kit.plugin.cassette.record
```

Concrete additions to v0.12:
- **`a2kit.get_tracer()`** — wraps `opentelemetry.trace.get_tracer("a2kit")`,
  cached. Plugins import from a2kit, not raw `opentelemetry`. One-line
  dependency, easy to mock in tests.
- **`@a2kit.plugin_span("name")` sugar** — decorates a provider method with
  `with tracer.start_as_current_span(f"a2kit.plugin.{name}"):`. Optional;
  the 20% case (custom span shape) just uses the tracer directly.
- **Convention for span attributes** — providers SHOULD set
  `a2kit.plugin.name` plus their own (e.g. `connection.key`). Documented in
  the plugin authoring guide. Not enforced by Protocol — encouraged by
  example in shipped plugins (Connection, future Cassette).
- **No Plugin Protocol change.** The contract from the DI section stands.

### structlog — adopt for `get_tool_logger`

User pre-validated. Replaces stdlib `LoggerAdapter` plan. The
`tool.name` / `connection.key` context becomes `structlog.contextvars.bind_contextvars`
calls inside the prelude, auto-correlating with the OTel span.

### v0.12 implementation order (revised)

1. **CLI `RegisterBlock` ParamType** — small, isolated, deletes 50 lines. Land first.
2. **`a2kit/di.py`** — Provider Protocol, Plugin Protocol, PluginBase. Pure
   types + helpers, no wiring yet. ~80 LOC.
3. **`MCPRunner.provides=` + `plugins=` kwargs.** Compile at `_prepare()`, not
   `__init__`. ~70 LOC of runner changes.
4. **Top-level `@a2kit.list/read/write` wrappers.** Each ~30 LOC.
5. **`@MyRouter.list`** (joining existing `.read`/`.write`).
6. **Refactor connection lookup** to consult the runner's type index instead
   of the per-tool `store=` kwarg.
7. **Lint additions:** A2K015 (`server=`), A2K016 (`store=`), extend
   `is_a2kit_tool_decorator` for verbs.
8. **OTel exception pattern** + `_NullSpan` no-op methods + `tool.result.count`.
9. **structlog `get_tool_logger`** with contextvars binding.
10. **Bump 0.12.0.dev0 + CHANGELOG + README rewrite.**

Connection-as-plugin extraction: deferred to v0.13. v0.12's surface is already
plugin-shaped; v0.13 = internal refactor + new `ConnectionsPlugin` bundling
three concerns (providers, routers, CLI). Mostly invisible to authors who
already adopted v0.12's surface.

---

## v0.13 — Composition Root collapse (design lock — 2026-05-08)

**Final v0.13 shape.** Three orthogonal primitives, App is the composition
root, no Plugin / Module abstraction.

### Why this shape

Iteration history that landed here:

1. **v0.12 brainstorm:** introduced `Plugin` to bundle providers + CLI + lifecycle.
2. **2026-05-08 pivot #1:** "Maybe there's no such thing as a plugin? Maybe it's
   just a Router?" → collapse `Plugin` into `Router`, add `provides=` and
   `cli_commands` to Router.
3. **2026-05-08 pivot #2:** "Should `provides` be bound to a Router? Maybe it's
   not a Router anymore then. Composition root maybe." → drop the bundling
   abstraction entirely. `App` is the composition root.
4. **2026-05-08 pivot #3:** "Should we register CLI commands separately?
   Shouldn't we derive CLI commands from tools as a convention?" → kill
   `click.Command` as a primitive. CLI is fully derived from tools.

### The two primitives

| Primitive  | Job                    | How it's contributed |
|------------|------------------------|----------------------|
| `Provider` | Produce a typed value  | `app.use(provider)`  |
| `Router`   | Group MCP tools        | `app.use(router)`    |

`app.use(*items)` accepts only these. **Deleted in v0.13:** `Plugin`,
`PluginBase`, `MCPRunner(plugins=...)`. **Never introduced:** `Module`,
free-floating `click.Command` registration.

### CLI is tool-derived; surfaces are capabilities

`App` auto-builds a Click group:
- `serve` (built-in) — start the MCP server
- One subcommand per registered tool — `app <tool-name> key=value ...`

**Surfaces folded into capabilities.** Add two built-in caps: `surface.mcp`
and `surface.cli`. Every tool is tagged with both by default. The existing
`--select` grammar handles all routing:

```
serve   default-select: "default and not write and surface.mcp"
cli     default-select: "default and surface.cli"
```

Per-tool overrides via verb-decorator shortcuts:

```python
@MyRouter.write(expose_to_cli=False)   # removes surface.cli from this tool
@MyRouter.read(expose_to_mcp=False)    # removes surface.mcp from this tool
```

Router-level defaults flow down: `class MyRouter(Router): default_caps = {Cap.SURFACE_CLI}`
makes all child tools CLI-only unless they re-add `surface.mcp` explicitly.

`login` / `logout` / `connections list` are tools on `ConnectionsRouter`,
both surfaces by default. The full `cap.write and todo` style of selection
works uniformly over surfaces too: `--select "surface.mcp and not write"`.

One implementation, two surfaces, one selection grammar.

### "Modules" are factory functions, not types

Cohesion = a Python module exporting a `make(...)` (or similar) that returns
a `list` of mixed primitives. No runtime contract — the only protocol is
"each item must be a Provider, Router, or click.Command."

```python
# a2kit/contrib/connections/__init__.py
def make(
    conn_type: type[ConnectionInfo],
    *,
    config_dir: Path | None = None,
) -> list[Provider | Router]:
    return [
        ConnectionStoreProvider(conn_type, config_dir),
        ConnectionsRouter(conn_type),  # tools default-expose to MCP + CLI
    ]

# Author:
import a2kit
from a2kit.contrib import connections

app = a2kit.App("todos-mcp")
app.use(*connections.make(TodoConn))
app.use(TodosRouter)
app.run()
```

Per-tool exposure (`expose_to_mcp=False` / `expose_to_cli=False`) lives on
the verb decorators inside `ConnectionsRouter`. Headless / read-only-FS
deployments subclass `ConnectionsRouter` and override per-tool toggles
(rare; defaults are fine for almost everyone).

### `app.connect()` — kept as sugar

`app.connect(TodoConn)` stays as a one-liner alias for `app.use(*connections.make(TodoConn))`
with both toggles default-on. Ergonomic shorthand, not a deprecation shim.

### Slim core runner

`MCPRunner` in v0.13 knows about: argv (`--http`, `--scope`, `--select`),
routers, providers, CLI commands, transport. Connection vocabulary is gone
from the core. `--register` moves to a tool exposed by `ConnectionsRouter`
(or to its own CLI subcommand under the connections group).

### Step 6 (chained DI) — what this locks

Step 6 builds the chained DI on the existing `provides=` list. The list lives
on `MCPRunner` in v0.12, gets renamed/moved through `App.use()` in v0.13, but
the resolution algorithm — `_provider_dep_types(provider)` + topo-sort + per-call
cache — is identical in both. Step 6 work is forward-compatible.

### Migration

v0.12 → v0.13:
1. `MCPRunner(provides=[...])` → `app.use(provider)` (or `App.use(*list)`).
2. `MCPRunner(plugins=[...])` — **deleted**. Each plugin becomes a `make()`
   factory in `a2kit.contrib.<name>`, called via `app.use(*module.make(...))`.
3. `Plugin`, `PluginBase` Protocols — **deleted** from `a2kit.di`.
4. `app.connect(TodoConn)` keeps working as sugar.
5. Tools annotated `*, todos: TodoStore` start working (chained DI, step 6).
   `*, conn: TodoConn` keeps working unchanged.

### v0.13 also-cleanup (compat carryover from v0.12)

Items deferred from the v0.12 "remove all compat" pass because they touch
50+ test sites and need a coordinated migration:

- **`@a2kit.tool(connection_param=<name>)`** — soft-deprecated since v0.9
  ("drops in v0.10" per the source comment, kept past v0.10). Migrate all
  tests to v0.9+ typed-info DI form (`*, info: MyConn`) and delete the
  kwarg + `_prelude`'s `elif connection_param is not None:` branches in
  `tools/_decorator.py`.
- **A2K005 (`KEY_FIELDS` migration aid)** — leftover lint rule from v0.5.
  Once no live code uses `KEY_FIELDS`, remove the rule + the `key_fields_value`
  / `connection_info_key_class` AST helpers + dedicated tests.
- **`ConnectionInfo` rename to `ConnectionConfig`** — per Denis's "what does
  *info* mean here" callout. ~25 files including user-facing examples and
  lint rule docstrings. Rename the base class, keep `ConnectionInfo` as a
  deprecated alias for one cycle (then delete in v0.14).
- **README/CHANGELOG soft-deprecation footnotes** — sweep for "soft-deprecated"
  / "removed in vX" notes for items already removed.

### v0.13 also-add: enrichers at router/app scope

Currently `@a2kit.tool(enricher=...)` is per-tool, repetitive when the same
enricher should apply to every tool in a router (or app-wide).

```python
app = a2kit.App("todos-mcp", enricher=chain(connection_enricher, generic_404))
class TodosRouter(a2kit.Router):
    enricher = chain(todo_403_enricher)   # composed with app's

@TodosRouter.read()
async def get_todo(...): ...               # gets app + router enrichers, no decoration
```

Resolution order: **tool > router > app**. Each level can `chain(...)` to
compose rather than replace. Tool-level `enricher=...` replaces (or composes
explicitly via `chain(parent_enricher, ...)`).

Touches: `Router` (new optional `enricher: EnricherFn | None` field), `App`
(new ctor kwarg), `tools/_decorator.py` (consult router_context + app on
exception path), tests.

### Pull connections out of core (the big one)

Surfaced 2026-05-08 mid-Step-6: the tool decorator's `_prelude` / `_prelude_async`,
`info_target` detection, `needs_connection_arg`, `WriteNotAllowed` enforcement,
`Router.store`, `MCPRunner.store=` are all connection-aware. The Composition
Root pivot intends `Provider` / `Router` as the only kit primitives; connections
should live entirely in `a2kit.contrib.connections`.

Concrete v0.13 work:
1. Replace `_prelude_async`'s connection logic with a generic provider-resolution
   pass over `provider_targets`.
2. Move `_lookup_connection_async`, `_resolve_info_strings`, `_resolve_connection_key`
   into `contrib.connections` as helpers consumed by `ConnectionStoreProvider`.
3. Move `WriteNotAllowed` enforcement onto the `ConnectionsRouter` (post-load hook
   on the provider).
4. Move `--register` argv handling out of `MCPRunner` into the connections module.
5. `Router.store` → deleted; auto-wiring lives in the connections module's `make()`.
6. `MCPRunner.store=` kwarg → deleted; connections become a regular Provider.

After: tool decorator has zero connection vocabulary. Tools annotate
`*, conn: TrackerConn` — that's a normal Provider request, no special path.

### Wire chained-DI auto-injection into tool decorator

Step 6 shipped the resolver machinery (`runner.resolve()`, contextvar) but
the tool wrapper doesn't yet auto-inject `*, store: TrackerStore`. Wiring this
through the v0.12 connection-aware decorator was the work that triggered the
Composition Root pivot. v0.13 plan: do this as part of the connections-out
refactor — by then the decorator is generic and the wiring is straightforward.

Sketch (kept here for next session):
- `_detect_provider_param_targets(sig, fn, info_target_name)` — non-ConnectionInfo
  typed kwonly params with a registered provider.
- `_inject_provider_params(targets, kwargs, loaded_conn, tool_name)` — at call
  time, check `_CURRENT_RUNNER`, resolve each, seed cache from `loaded_conn`.
- Sync tools with provider params raise at decoration time (provider resolution
  is async-only).
- Hide provider params from the published Click/MCP signature.

### PLC0415 audit — ban lazy imports from src/

`src/a2kit/**` has 55 occurrences of `# noqa: PLC0415`. Audit each:
- Optional-dep loading (FastMCP, OTel, structlog) — keep but document the dep.
- Click subcommand bodies — move to module top unless there's a measured cost.
- Circular-import workarounds — fix the circular import at the architecture level.
- Habit imports — delete the noqa, move to top.

After audit: drop `PLC0415` from `tests/**` per-file ignore (tests should also
import at top), and remove all surviving per-line noqas.

### Coverage hole — restore to 100%

Two lines uncovered after the v0.12 ty-fix refactors:
- `src/a2kit/enrichers.py:108` — sync wrapper closing async coroutine before
  re-minting in the drain thunk. Test: sync `@a2kit.tool` with an async
  enricher; raise inside the body; expect the async enricher's exception.
- `src/a2kit/tools/_signature.py:113` — `pagination=Passthrough` adds
  `limit`/`cursor` to expected params. Test: tool decorated with
  `pagination=Passthrough` but missing `limit` kwonly param → expect kit error
  about missing passthrough params.

Restore `cov-fail-under=100` in `pyproject.toml` once these land.

### App.use(Plugin) — delete the Plugin arm

Currently `App.use()` accepts `Plugin` as a fallback. v0.13 deletes `Plugin` /
`PluginBase` entirely (Composition Root has only `Router` + `Provider`). The
`else` branch + `_plugins` list go away.

### Already removed in v0.12 (Step 6 + this pass):
- `a2kit.errors` deprecation shim (was: re-export of `a2kit.enrichers`).
- Stale "re-exported from `a2kit.enrichers` for backward compatibility"
  docstring claim on `ConnectionInfoLike` / `ConnectionStoreLike` (the
  re-export wasn't actually live).
- v0.11 backward-compat tests for the above.

---

## v0.13 — full plan: deletes, swaps, pattern shift (2026-05-08)

Captured after the architectural-scan exchange. This supersedes the earlier
"v0.13 also-cleanup" lists; treat as the single execution plan for v0.13.

### Headline pattern shift: `Annotated[T, Depends(factory)]` everywhere

The whole DI surface (Provider, type-based auto-injection, `_detect_info_param`,
`info_target`, `Generic[ConnT]`, `auto_connection_enricher`) collapses into the
FastAPI/FastMCP idiom:

```python
from typing import Annotated
from a2kit import Depends            # ~10-LOC marker class

# In the connections plugin:
async def get_conn(connection: str) -> TrackerConn:
    """Load a saved connection by key. The kit makes `connection` a kwonly
    str arg on every tool that depends on it (transitively)."""
    return await _connections_store.get_async(_resolve_connection_key(connection))

async def get_todo_store(
    conn: Annotated[TrackerConn, Depends(get_conn)],
) -> TodoStore:
    return TodoStore(conn)

# In user code:
@TasksRouter.write()
async def create_task(
    store: Annotated[TodoStore, Depends(get_todo_store)],
    title: str,
) -> Task:
    ...
```

How the kit resolves it (no third-party DI lib):
1. At decoration time: `inspect.get_type_hints(fn, include_extras=True)` →
   for each `Annotated[T, Depends(factory)]` param, store `(name, factory)`.
2. At call time: walk factories, call each (with their own deps resolved
   recursively), per-call cache.
3. Cycle detection identical to today's `_check_no_cycles`.
4. Test override: `app.dependency_overrides[get_conn] = lambda: TrackerConn(db_path="/mem")`.

`Depends(factory)` is a frozen dataclass — that's the entire DI library:

```python
@dataclass(frozen=True, slots=True)
class Depends:
    dependency: Callable[..., Awaitable[Any]] | None = None
    use_cache: bool = True
```

Deletes:
- `a2kit.Provider`, `a2kit.PluginBase`, `a2kit.Plugin`
- `a2kit.Binding`, `a2kit.ToolPlan`
- `a2kit.ProviderCollisionError`, `a2kit.UnknownProviderTypeError`,
  `a2kit.UnknownProviderDepError`, `a2kit.ProviderCycleError`
- `MCPRunner.lookup_provider`, `MCPRunner.resolve`,
  `MCPRunner._build_provider_index`, `MCPRunner._provides`,
  `MCPRunner._plugins`
- `_CURRENT_RUNNER` contextvar (replaced by `_current_app` if needed for
  override lookup; cleaner than runner-keyed)

The resolver from di.py (`resolve_chain`, `_validate_provider_graph`,
`_check_deps_resolvable`, `_check_no_cycles`, `_provider_dep_types`) is
**rewritten** for `Annotated[T, Depends]` shape (different inspection,
same algorithm). ~150 LOC net, all in one file.

### Headline architectural pattern: implicit middleware chain

Today's `tools/_decorator.py` is a 380-line function doing connection
loading, capability check, write enforcement, ctx push, list-view extract,
OTel span, enricher chain, signature splice, format detection. Replace with
a Starlette-style middleware chain — but **assembled implicitly** so authors
write zero middleware boilerplate in the 99% case.

**Convention over configuration**: the kit assembles the chain at decoration
time from the verb (`@list`/`@read`/`@write`), the Router's config
(`enricher` field set or not), and the active connection (`read_only` or
not). Authors describe *what* the tool does; the kit handles *how*.

#### Three tiers of middleware presence

**Tier 1 — Always-on (verb baseline):**
Every tool, no opt-in needed:
- `OTelSpan` — opens span around tool body
- `ToolCallGuard` — detects accidental tool-call contamination in args
- `CapabilityGuard` — checks tool is in the active select expr

**Tier 2 — Conditionally implicit (kit decides from context):**
- `WriteEnforce` — added iff `@write()` AND resolved connection has `read_only=True`
- `ListViewApply` — added iff `@list()`
- `EnrichErrors` — added iff Router OR App has `enricher=` set
- `FormatResponse` — added iff return annotation gives the kit a format hint

**Tier 3 — Explicit (rare; author opts into extras):**
- `Router.middleware = [audit_log]` — appended to the implicit chain
- `App.middleware = [global_log]` — app-wide append
- `@MyRouter.write(middleware=[mw])` — per-tool extras
- Opt-out flags: `@MyRouter.read(otel=False)`, `bare=True` skips all implicit

#### Middleware shape

```python
async def mw(
    call_next: Callable[..., Awaitable[Any]],
    ctx: ToolContext,
    /,
    **kwargs: Any,
) -> Any: ...
```

`ToolContext` is a frozen dataclass passed through middleware: tool name,
verb, write flag, capabilities, format hint, dependency cache, the loaded
connection (when present). Every middleware is unit-testable without a live
router.

#### What the user actually writes (99% case)

```python
class TasksRouter(a2kit.Router):
    """Tasks tools. Slug auto-derived. Zero middleware config."""
    enricher = tracker_404_enricher        # ← only line that's not pure data

@TasksRouter.write()                        # auto-stacks: Write+Cap+OTel+Guard+Enrich
async def create_task(
    store: Annotated[TodoStore, Depends(get_todo_store)],
    title: str,
) -> Task: ...
```

That's the entire surface. No `middleware = [...]` list, no decorator stack,
no plumbing. The kit reads `@write()` + Router has enricher + connection
might be read-only and assembles the chain.

#### What the kit code looks like

```python
def _build_chain(verb: Verb, router: Router, app: App, write: bool) -> list[Middleware]:
    chain: list[Middleware] = [tool_call_guard, capability_guard, otel_span]
    if write:
        chain.append(write_enforce)
    if verb == "list":
        chain.append(list_view_apply)
    enricher = router.enricher or app.enricher
    if enricher is not None:
        chain.append(enrich_errors_factory(enricher))
    chain.extend(router.middleware)        # tier-3 extras
    chain.extend(app.middleware)
    return chain
```

The tool decorator becomes ~30 lines:
1. Inspect signature for `Annotated[..., Depends(...)]`.
2. Compute middleware chain via `_build_chain`.
3. Wrap fn in chain (right-to-left composition).
4. Hide `Annotated` deps from published Click/FastMCP signature.

Deletes:
- `_prelude` and `_prelude_async` (the 80-line monsters)
- `_detect_info_param`, `info_target`, all "info" vocabulary in core
- `needs_connection_arg` branch logic
- `_check_tool_call_contamination` (becomes a middleware)
- `connection_param=` legacy kwarg
- `auto_connection_enricher` field on Router
- `Router(BaseModel, Generic[ConnT])` Generic dance

### Headline mounting pattern: sub-apps, not plugins

The legacy `Plugin` Protocol gets deleted (already locked). Connections
become a **sub-app**:

```python
# in a2kit.contrib.connections:
def make(conn_type: type[ConnectionInfo], *, config_dir: Path | None = None) -> a2kit.SubApp:
    sub = a2kit.SubApp("connections")
    sub.use(ConnectionsRouter(conn_type))   # tools: register, list, show, delete
    sub.depends[get_conn] = make_get_conn(conn_type, config_dir)
    return sub

# in user code:
app = a2kit.App("tracker-mcp")
app.mount(connections.make(TrackerConn))
app.use(TasksRouter)
app.run()
```

`SubApp` is a Router collection + a `dependency_overrides`-shaped map. It
mounts cleanly into the parent App's CLI (Click sub-group), MCP tool list,
and DI cache. Inspired by Starlette's `app.mount(...)`.

### Library deletes / replacements

Locked. Done early in v0.13:

| Concern | Today | Replace with | Reason |
|---|---|---|---|
| Sync→async drainage | `_async_bridge.py` (18 LOC) | `anyio.from_thread.run` direct | stdlib equivalent; we re-implemented |
| OTel NoOp fallback | `_otel.py` `_NullSpan` (~150 LOC) | `opentelemetry.trace.NoOpTracer` | OTel ships this; we duplicate |
| VCR cassettes | `_cassette.py` (~40 LOC) | `vcrpy` direct | already a dep |
| CEL select grammar | `_select*.py` (~600 LOC) | `cel-python` direct (already dev dep!) | mature, the syntax users learn becomes real CEL |
| ENV / op:// resolution | `tokens.py` (~60 LOC) | `pydantic-settings` (ENV) + `pyonepassword` (op://) | best-in-class for each |
| DI container | `di.py` (~280 LOC) | `Annotated[T, Depends]` (~30 LOC inline) | FastAPI idiom, no new deps |

Net delete: ~1100 LOC of bespoke parsers / containers / wrappers.

### CLI rewrite: typed `RunnerOptions`

Today: `App.cli` (Click) → builds `runner_argv: list[str]` → `MCPRunner.run(argv=...)`
→ `_parse(argv)` re-parses with hand-rolled walker.

After:
```python
@dataclass(frozen=True, slots=True)
class RunnerOptions:
    http: str | None = None
    select_expr: str | None = None
    scope: str | None = None
    transport: Literal["stdio", "http"] | None = None

# App.cli's serve subcommand:
@group.command("serve")
@click.option(...)
def serve(http, select_expr, scope):
    options = RunnerOptions(http=http, select_expr=select_expr, scope=scope)
    self._runner.run(options=options)

# MCPRunner.run signature:
def run(self, *, options: RunnerOptions = RunnerOptions()) -> None: ...
```

Deletes:
- `MCPRunner._parse` (30-line state-machine argv walker)
- `MCPRunner._http_settings`
- `_parse_multistore_register` walker
- `register_ephemeral_connections` (logic moves to `connections register` Click subcommand)
- `--register` argv flag (replaced by `connections register` subcommand)

### Magic surfaces removed (single-line summary each)

| Magic | Replacement |
|---|---|
| `_detect_info_param` (find `*, conn: TrackerConn`) | Explicit `Annotated[T, Depends(factory)]` |
| `info_target` plumbed through 5 functions | Gone — there is no special "info" param |
| `_lookup_connection_sync` AND `_lookup_connection_async` parallel | One async path; sync tools that need a conn raise at decoration |
| Auto-stamp `_a2kit_capabilities` / `_a2kit_tool_name` / `_a2kit_format` on user fn | `WeakKeyDictionary[fn, ToolMetadata]` registry |
| `list = list_tool` shadowing builtin | Verb names: `list_tool`/`read_tool`/`write_tool` everywhere |
| `Router(BaseModel, Generic[ConnT])` TypeVar | Plain Pydantic Router, no Generic |
| `auto_connection_enricher` flag | Explicit `enricher=` if wanted; default None |
| `connection_param=<name>` kwarg | Deleted |
| `Router.store` auto-wiring from single registered store | Deleted (use `Annotated[ConnectionStore, Depends(...)]`) |
| `_prelude_async` doing 8 things | Middleware chain, each step ~10 LOC |

### `tests/**` cleanup

After CompRoot + middleware, the bespoke `_FakeServer` / `_FakeStore` /
`_FakeProvider*` test doubles across the suite become a single
`app.dependency_overrides`-style map. Migration:

1. Add a top-level fixture: `def app(request) -> a2kit.App: ...` that builds
   a real App + real ConnectionStore on `tmp_path`.
2. Tests that need fakes call `app.dependency_overrides[get_conn] = ...`.
3. Delete `_FakeProviderForA`, `_FakeProviderForB`, `_OtherProviderForA`,
   `_FakeServer`, etc.

### Coverage-hole tests (restore to 100%)

Already noted: enrichers.py:108 (sync-wrapper-around-async-enricher coro
close), tools/_signature.py:113 (Passthrough pagination missing-param check).
After the middleware refactor, the enrichers path moves into a middleware
and tests are easier to write. Restore `cov-fail-under=100` post-refactor.

### PLC0415 ban

Audit + ban from `src/`. Drop `PLC0415` from `tests/**` per-file ignore too.
Each surviving lazy import either justifies itself (optional dep, circular
broken at architecture level) or moves to top.

### Sequencing — 6 phases

1. **DI swap** (1 commit): Implement `Depends`, `dependency_overrides`,
   resolver. Decorator detects `Annotated[T, Depends]`. Old `Provider`
   surface deprecated but kept for one cycle (callers still work).

2. **Middleware extraction** (1 commit per middleware): Pull `OTelSpan`,
   `CapabilityGuard`, `WriteEnforce`, `EnrichErrors`, `ListViewApply` out
   of `_prelude_async` one at a time. Each commit shrinks `_prelude_async`.

3. **Connections plugin extraction** (2-3 commits): `a2kit.contrib.connections`
   with its own SubApp, ConnectionsRouter, `get_conn` factory, login/logout
   tools. `app.connect(T)` becomes sugar for `app.mount(connections.make(T))`.

4. **CLI rewrite** (1 commit): Delete `MCPRunner._parse`, introduce
   `RunnerOptions`. Move `--register` to a `connections register` tool.

5. **Library swaps** (1 commit each): `_async_bridge.py` → anyio,
   `_otel.py` → NoOpTracer, `_select*.py` → cel-python, `tokens.py` →
   pydantic-settings + pyonepassword, `_cassette.py` → vcrpy direct.

6. **Cleanup** (1 commit): Delete `Plugin`/`PluginBase`/`Provider`,
   `_detect_info_param`, `connection_param=`, `auto_connection_enricher`,
   `Generic[ConnT]`, `list = list_tool` shadow. Restore `cov-fail-under=100`.
   PLC0415 audit. Bump to 0.13.0.dev0.

Each phase ships green. Tests + lint + ty + a2kit-lint pass at every
commit boundary.

### Backward compatibility

Hard break. v0.13 is a major surface change. Migration guide in CHANGELOG;
no compat shims (the user's "remove all deprecated/back-compat stuff"
preference applies here too).
