# a2kit — v0.11+ todo

Captured from contract / asyncio / OTel audit (2026-05-08, post v0.10.0).

---

## Deferred: SubApp / connection-as-plugin (was v0.13's `connections.make`)

The v0.13-era `connections.make(TodoConn)` placeholder factory in
`a2kit.contrib.connections` was deleted in v0.19 — it returned an
unconsumed tuple and only existed as a syntax stub for an unbuilt
SubApp surface. If/when SubApp / mount-style plugin composition
lands, introduce the new shape directly; authors keep using
`app.connect(conn_type)` until then.

---

## v0.18 spike — FastMCP request-id → OTel `mcp.request_id`

**Outcome: blocked by FastMCP coupling. Closed 2026-05-08.**

`mcp.server.fastmcp.Context.request_id` (str, from
`request_context.request_id`) does expose the MCP JSON-RPC request ID
to tool wrappers. FastMCP injects `Context` into a tool *only when the
tool function declares a `Context`-annotated kwarg* — see
`mcp.server.fastmcp.tools.base.Tool.run`, which threads `Context` via
`{context_kwarg: context}` keyed on a precomputed `context_kwarg`.

Wiring this into a2kit's OTel middleware would require:

1. The kit detecting a `Context`-annotated kwarg on the wrapped fn at
   decoration time.
2. The middleware reading that kwarg out of `**kwargs` and calling
   `.request_id` on it.

Both steps need a2kit to import `mcp.server.fastmcp.Context` —
contradicting the v0.11 `FastMCPLike` Protocol design (the kit does
*not* depend on FastMCP at runtime; FastMCP is a dev dep only). Adding
runtime FastMCP coupling for one span attribute isn't worth it.

Plausible follow-up paths if this becomes important:

- A `bare_request_id` shim that hosts opt into via a kwarg on
  `@a2kit.tool(request_id_param="ctx")` — pure string lookup, no
  FastMCP import. ~10 LOC; defer until a real consumer asks.
- Upstream FastMCP middleware/hook surface that exposes the request ID
  to wrapper-style libraries (currently absent — would be a FastMCP
  feature request).

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

- [x] **Fix `format_from_annotation` decision-tree gaps** — landed v0.17. Bare `dict` / `Mapping[...]` / `TypedDict` → `"json"`. `Awaitable[T]` / `Coroutine[Y, S, T]` unwrapped before classification.
- ~~**`Page[Union[A, B]]`** falls to runtime silently. Add test + log.~~ — partially-landed v0.17: multi-arm Union handling in `_flat_pydantic_fields` covers the same root cause; `Page[Union[A, B]]` itself is exotic enough that runtime fallback is acceptable. Reopen if a real consumer hits it.
- [x] **`_dump_items` silently drops non-dict/non-BaseModel** — landed v0.17. Raises `TypeError` with index. `format_response` gates the call so heterogeneous lists fall through to JSON.
- [x] **`_flat_pydantic_fields` Union-stripping** — landed v0.17. Multi-arm `Optional[Union[A, B]]` examined per-arm via new `_classify_arm` helper.
- ~~**Drop runtime `_is_uniform_row_list` cross-check** when `_a2kit_format` is set. Trust decoration; let tool bugs surface.~~ — STALE: `_a2kit_format` stamping replaced by middleware-resolved format hint in v0.13; `_encode` already trusts the hint when shape-compatible.

## P1 — verification (Hypothesis)

- [x] **Property test**: `format_from_annotation(T)` precompute ↔ `toon_or_json(model_dump(instance))` runtime agree for any Pydantic model. — landed v0.17 in `tests/test_v17.py`.
- [x] **Property test**: `truncate(x)` is structural identity except str clipping; never mutates input. — landed v0.17 in `tests/test_v17.py`.
- ~~**Property test**: `_coerce_key` accepts {kwargs, tuple, list, NamedTuple, single-string-when-arity-1}; rejects everything else with typed error.~~ — STALE: `_coerce_key` no longer exists; key resolution moved into `contrib.connections._helpers` and is exercised by `test_connections.py` shape tests.

## P2 — asyncio-first

- [x] **Async connection-store API** (`connections.py:288-315`) — landed v0.11. `ConnectionStore.load`/`save`/`list_connections`/`list_keys` are all `async def`; sync callers drain via `anyio`.
- ~~**Switch `_lookup_connection`** (`tools.py:202-208`) to await async variant from `async_wrapper`.~~ — STALE: `tools.py` is gone; `_lookup_connection_async` lives in `tools/_connection.py` and is the canonical async path. Sync wrapper drains it via `anyio.from_thread.run`.
- [x] **`MCPRunner.run_async()`** for embedding into existing event loop. — landed; `App.run_async` and `MCPRunner.run_async` are both implemented (`scaffold/_runner.py:354`, `app.py:328`).
- ~~**`_TRANSPORT_LOCAL` → ContextVar** (`tools.py:81-92`) for consistency with `_RouterContext`.~~ — STALE: `_TRANSPORT_LOCAL` and `_RouterContext` are both gone; transport plumbing collapsed into `RunnerOptions` in v0.13 phase 4.
- [x] **`EnricherFn` accepts async**: `Callable[..., Exception | Awaitable[Exception]]`. — landed v0.11. Type alias in `enrichers.py:49` already broadened; sync wrapper drains via `anyio` 3-tier fallback.

## P2 — OTel / observability

- [x] **Record exceptions on the span** — landed via OTel default. `start_as_current_span` ships `record_exception=True, set_status_on_exception=True` by default; the v0.13 middleware refactor moved the `try/except` outside the span CM (the middleware re-raises through the span). Verified in `middleware/_otel.py`.
- ~~**`a2kit.get_tool_logger(name)`** — `LoggerAdapter` injecting `tool.name` + `connection.key`.~~ — DEFERRED to v0.18: structlog adoption is a 200+ LOC rabbit hole (contextvars binding + plugin docs + test migration); not justified standalone.
- [x] **`tool.result.count` span attribute** when result is list/`Page` (cardinality only — PII safe). — landed v0.17 in `middleware/_otel.py`.
- [x] **Provider-class string check is fragile** (`_otel.py:64`). — accepted as-is. `_resolve_tracer` (`_otel.py:50`) checks both `ProxyTracerProvider` and `NoOpTracerProvider` by class name; the `isinstance` form would still need the `try/import` fallback. Coverage exercises this path.
- ~~**Spike**: does FastMCP expose MCP JSON-RPC request ID?~~ — DEFERRED to v0.18: speculative, no consumer asking.

## P3 — internal cleanup (deferred from review)

- ~~Move `_check_tool_call_contamination` str-typed param set to decoration time (`tools.py:541-544`).~~ — STALE: `tools.py` is gone; check is now a `tool_call_guard` middleware (`middleware/_guards.py`) computing the param set fresh per call (small overhead, simpler).
- ~~`_auto_inject_enabled` cache → `functools.cache`-wrapped fn (`tools.py:790`).~~ — STALE: `_auto_inject_enabled` deleted with the v0.15 typed-info DI removal.
- ~~`_resolve_store(self, fallback)` helper to dedupe 3x two-tier fallback in scaffold.~~ — STALE: `MCPRunner.store=` and `Router.store` were deleted in v0.15; no two-tier fallback remains.
- ~~Tighten `Iterable[ConnectionInfoLike]` → `Sequence` on Protocol (or materialize internally).~~ — STALE: already `Sequence[ConnectionInfoLike]` in `connections.py:79` (landed v0.11 bonus).
- ~~Document `chain(*enrichers)` first-transforms-wins semantics + lock with short-circuit test.~~ — STALE: documented in `enrichers.py` module docstring + `chain` docstring; `test_enrichers.py` covers short-circuit semantics.
- ~~Deprecate tuple/list arms of `_resolve_connection_key` (`tools.py:155-164`); v0.12 delete.~~ — STALE: function moved to `contrib/connections/_helpers.py` and the legacy arms were trimmed.
- ~~MAX_DISPLAYED_CONNECTIONS module constant in `docs.py` (was deferred from v0.10 review).~~ — STALE: `docs.py` was reshaped post-v0.13; constant no longer relevant.
- ~~Schema-staleness doc note on `connection_enricher` (decoration-time keys).~~ — STALE: `connection_enricher` is now async and reads keys at *call* time via `await store.list_connections()` — the staleness premise is gone.
- ~~Lint rules A2K001-A2K013 update for v0.10 patterns.~~ — STALE: lint suite was rebaselined in v0.13/v0.14; A2K005 deleted, A2K015/A2K016 added; rules track current surface.

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
| CEL select grammar | `_select*.py` (~600 LOC) | `cel-python` direct (already dev dep!) | mature, the syntax users learn becomes real CEL — **DEFERRED in v0.13 phase 5** (see below) |
| ENV / op:// resolution | `tokens.py` (~60 LOC) | `pydantic-settings` (ENV) + `pyonepassword` (op://) | best-in-class for each — **DEFERRED in v0.13 phase 5** (see below) |
| DI container | `di.py` (~280 LOC) | `Annotated[T, Depends]` (~30 LOC inline) | FastAPI idiom, no new deps |

Net delete: ~1100 LOC of bespoke parsers / containers / wrappers.

#### `_select*.py` → `cel-python` — deferred (v0.13 phase 5)

Probed the swap and stopped before touching code. Two structural blockers:

1. **Grammar divergence is user-facing.** Our select uses `and` / `or` / `not`
   keywords; CEL uses `&&` / `||` / `!`. Our atoms use `tool:foo` / `cap:foo`
   namespacing; `:` is not a CEL operator. Atom keys with dots (`surface.mcp`)
   read as field access in CEL. We'd need either a translation pass (which
   replicates much of the parser we wanted to delete) or a hard breaking
   change to user-facing syntax across docs, examples, and `default_select`
   tomls — flagged by the plan as "don't break user-facing syntax silently."

2. **`SelectExpr` is a Pydantic AST consumed beyond evaluation.** The Pydantic
   AST is walked by `validate_atoms` (lint-time, with difflib suggestions for
   unknown caps), by lint rules in `lint/_rules_collisions.py` and
   `lint/static.py`, and by scaffold/runner introspection (~100 references
   across src + tests). cel-python returns an opaque compiled program, not a
   walkable AST in the same shape. Replacing only the *evaluator* (keeping our
   parser+AST) saves ~70 LOC out of 600 — not worth the new dep on the runtime
   path.

   To actually capture the win, the swap needs to come bundled with: (a) a
   user-facing CEL-grammar migration (operators + namespacing), (b) a rewrite
   of every `validate_atoms`-style introspection pass against CEL's AST shape,
   and (c) re-baselining the lint rules. That's a v0.14+ shaped chunk, not a
   single library swap.

   Action: stays as-is for v0.13. Re-open as a dedicated pitch when the
   composition-root work is settled and the user-facing select grammar can
   move with deliberate timing.

#### `tokens.py` → `pydantic-settings` + `pyonepassword` — deferred (v0.13 phase 5)

Probed both libraries; both are mismatched to what `tokens.py` actually does.

1. **`pydantic-settings` is the wrong abstraction for `resolve_env`.** Our
   `resolve_env` does regex `${VAR}` substitution *inside arbitrary strings*
   (e.g. `prefix-${TOKEN}-suffix`), called lazily at API-call time on already-
   loaded `ConnectionInfo` field values. `pydantic-settings` is a typed
   settings-model loader: it pulls ENV into Pydantic fields at model-construct
   time. Different shape, different lifecycle. Adopting it would require
   reworking how `ConnectionInfo` itself is loaded, not a one-line swap.

2. **`pyonepassword` saves ~15 LOC at the cost of two new deps.** Our
   `resolve_op` is a 15-line `subprocess.run(["op", "read", value])` wrapper
   with three typed error paths (missing binary / non-zero exit / timeout).
   `pyonepassword` is itself a `subprocess.run` wrapper around the same `op`
   binary, plus `python-singleton-metaclasses`. The exception surface differs
   (we'd need to translate its errors into our `OpResolutionError`). For a
   ~15-line save we'd be adding two transitive deps to core install.

3. **`tokens.py` is not bespoke duplication.** Unlike `_NullSpan` (which OTel
   ships verbatim) or `_async_bridge.py` (which is `anyio.from_thread.run`
   spelled twice), `tokens.py` exposes a small but distinct primitive:
   pluggable string-resolver registry with regex-based predicates. There's
   no equivalent in the candidate libraries.

   Action: stays as-is for v0.13. The aspirational framing in the locked
   table didn't survive contact with the actual library APIs. Revisit if a
   genuine "shared by all" resolver lib emerges.

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

## v0.13 — final ledger (2026-05-08)

Released as `0.13.0.dev0`. The v0.13 plan above intended a hard break;
the actual release kept v0.12 surfaces alive as compat to keep the
test-corpus blast radius bounded. Items deferred to v0.14:

- **Hard delete `Router.store`, `MCPRunner.store=`, `connection_param=`,
  `_detect_info_param` / `info_target`, the `_prelude_async` connection
  branch, `Router(BaseModel, Generic[ConnT])`, `Plugin` / `PluginBase`
  Protocols.** Each touches 30–80 test sites that need migration to
  `Annotated[Conn, Depends(get_conn)]` + `app.dependency_overrides`. v0.14
  picks this up as one coordinated migration.
- **`SubApp` / `app.mount(connections.make(...))` shape.** Today's
  `connections.make()` returns a placeholder tuple and authors keep using
  `app.connect(conn_type)`. The proper sub-app + `connections register`
  CLI subcommand is v0.14 work.
- **`_select*.py` → `cel-python`.** Probed; deferred (see "DEFERRED in
  v0.13 phase 5" notes above).
- **`tokens.py` → `pydantic-settings` + `pyonepassword`.** Probed;
  deferred (see notes above).
- **Drop `PLC0415` from `tests/**` per-file ignore.** 123 ruff hits in
  the test corpus today; non-trivial migration. (Source-side audit
  landed: 49 → 25 noqas in `src/`, all genuinely circular / optional-
  dep / verb-decorator factory.)
- **A2K005, `ConnectionInfo` rename to `ConnectionConfig`,
  README/CHANGELOG soft-deprecation footnote sweep** — listed in the
  v0.13 also-cleanup section above; carried over to v0.14.
- **`enricher` at router/app scope.** v0.13 plan listed it as
  "also-add"; not implemented (would entangle with the deletes above).

What v0.13 *did* land:

- Phase 1: `Annotated[T, Depends(factory)]` resolver + `app.dependency_overrides`.
- Phase 2: implicit middleware chain (`a2kit.middleware`).
- Phase 3 (partial): `a2kit.contrib.connections` package with helpers and
  `WriteEnforce` middleware factory. Re-exports keep v0.12 import paths
  alive.
- Phase 4: `RunnerOptions` typed dataclass; `App.cli` skips argv
  round-tripping.
- Phase 5 (partial): `_async_bridge` → `anyio.from_thread.run`, `_NullSpan`
  → `opentelemetry.trace.NoOpTracer`, `_cassette` async-CM → `vcrpy`
  direct. (`_select*` and `tokens.py` swaps deferred.)
- Phase 6: 100% coverage restored (`cov-fail-under=100`); PLC0415 audit
  in `src/` (49 → 25); README + CHANGELOG refreshed; version bump.

Final state: 737 tests, 100% coverage, lint clean.

## v0.15 — in-progress ledger (2026-05-08)

v0.15 is the breaking-compat release that hard-deletes the v0.12
connection surface listed at the top of the v0.13 final ledger. Scope is
genuinely large — ~117 `connection_param=` test sites, 43 `Plugin`/
`PluginBase` references across 11 test files, plus interlocked source
deletes in `_decorator.py`, `_router_state.py`, `app.py`, `di.py`. The
session that opened v0.15 landed *foundation only*: future work picks
up here.

### What v0.15 has shipped so far

- **`a2kit.contrib.connections.get_conn_factory(app, ConnT)`** — the
  Annotated/Depends idiom for connection injection. Pairs with
  `app.connect(ConnT)`; tests override via
  `app.dependency_overrides[get_conn] = fake_get_conn`. Replaces the
  v0.12 `*, info: ConnT` autodetect path.
- **Tool decorator now exposes `connection` for Depends factories.**
  When any `Annotated[..., Depends(factory)]` kwonly's factory declares
  `connection: str` as a non-Depends kwonly, the wrapper injects
  `connection` as a kwarg and forwards it as call_ctx to the resolver.
  Pops it before the inner fn's signature guard runs.
- 4 new tests in `tests/test_v15_get_conn_factory.py` cover the factory
  + override path. 704 tests, 100% coverage, lint clean.

### What v0.15 still owes (to be continued in a follow-up session)

These are interlocked — the deletes are mechanical *once the test corpus
has migrated*. Suggested order:

1. **Migrate the example.** `examples/tracker/routers.py` is the canonical
   reference; switch to `get_conn = get_conn_factory(app, TrackerConn)`
   + `*, conn: Annotated[TrackerConn, Depends(get_conn)]`. Wire in
   `examples/tracker/server.py`.
2. **Add a shared `app` fixture in `tests/conftest.py`** that yields a
   real `a2kit.App` with `dependency_overrides` ready to populate. Goal:
   replace `_FakeStore` / `_FakeProvider*` with a uniform pattern.
3. **Migrate tests by category** (commit per file or small batch):
   - `connection_param=` (~54 hits across `test_v06.py`, `test_v07.py`,
     `test_v10.py`, `test_v11.py`, `test_v12.py`, `test_runner.py`,
     `test_tools_fat.py`, `test_v08.py`).
   - `*, info: ConnT` autodetect (varies; check via decorator-arg lookup).
   - `Plugin`/`PluginBase` Protocols (43 hits — likely many tests are
     pure Plugin-arm exercises and can be deleted, not migrated).
4. **Then delete source surface** — order matters:
   1. `connection_param=` from `@a2kit.tool` signature + `_prelude_async`
      branch.
   2. `_detect_info_param` / `info_target` plumbing.
   3. `Router.store` field + `MCPRunner.store=` kwarg.
   4. `Generic[ConnT]` from Router (plain Pydantic model).
   5. `Plugin` / `PluginBase` Protocols in `di.py` + Plugin arm of
      `App.use()`.
   6. (Optional) `Provider` Protocol if grep shows no live callers.
5. **Re-verify**: `_prelude_async` should drop from 55 LOC to ~20.
   `grep -r 'connection_param\|_detect_info_param\|info_target\|
   Router.store\|MCPRunner.store\|PluginBase\|Plugin Protocol' src/
   tests/` returns zero hits.
6. **CHANGELOG entry, version bump to `0.15.0.dev0`.**

### Known interlocks / sequencing risks

- `App._build_runner` still passes `store=self._stores[0]` to MCPRunner.
  Deleting `MCPRunner.store=` requires App to stop threading the store
  through; the connection store stays accessible via `app._stores` (or a
  public property) for `get_conn_factory` to read.
- `examples/tracker/` and the connection-management CLI (`build_cli`)
  still need a `ConnectionStore` reference for `login`/`logout`. The
  store doesn't disappear — only the tool-decorator coupling does.
- `_prelude_async` keeps the `connection_param` and `info_target`
  branches today as v0.12 compat. Deleting them is the headline LOC
  reduction; do it after the test corpus is fully migrated.

