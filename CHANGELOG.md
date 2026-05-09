# Changelog

## Next — LDD streaming reports + narrative events

### New ToolContext channels

- **`ctx.event(name, **payload)`** — typed narrative events. Free
  channel; any tool can emit. Wire format: MCP `notifications/message`
  with `data.a2kit_kind="event"`, `data.name`, `data.payload`,
  `data.elapsed_ms`. CLI: `[ +s.mmm event   ] name key=val`.
- **`ctx.report(payload)`** — typed mid-flight result chunks. Requires
  the verb decorator to declare `report=ReportT` (Pydantic model or
  TypedDict). Validated at call time — raises `ReportTypeMismatch` /
  `ReportTypeNotDeclared`. Wire: `data.a2kit_kind="report"`,
  `data.type`, `data.payload`, `data.elapsed_ms`. CLI:
  `[ +s.mmm report  ] TypeName key=val`.

### Wire format

- All CLI emissions (info / warning / error / debug / progress / event /
  report) now use `[ +s.mmm LEVEL] ...` format with relative elapsed
  timestamps from tool-call start.
- All MCP emissions carry `data.elapsed_ms: int` for client-side rendering.

### Kill-switch

- **CLI flags** `--no-reports` / `--no-events` at the top level —
  silence each channel for one invocation.
- **`App.set_ldd(reports=, events=)`** for programmatic control.
- **Env `A2KIT_LDD=off`** disables both channels process-wide.
- Most-specific layer wins: flag > app > env. Disabled emissions still
  type-validate `report=` payloads.

### Schema dump

- `<app> schema <tool>` now includes `reportSchema` (the JSON schema for
  the declared `ReportT`) when present.

### Lint

- New rule **`A2K-LDD-REPORT-TYPE`** — fires when `ctx.report(...)` is
  called without a `report=` decorator kwarg, or when the declared type
  is defined inside a function (Pydantic forward-ref constraint).

### Examples

- `examples/streaming_logger/` extended with `import_csv_with_reports`
  showing all four channels working together. README rewritten with the
  channel-decision table and kill-switch docs.

## 1.0.0 — protocol-agnostic core — 2026-05-09

Clean break. ~7.9K LOC → ~2.7K LOC. Protocol-agnostic core (~1K) +
opt-in plugin packages under `a2kit.packages.*` (~1.7K). FastMCP is
now a hard dependency, isolated to `a2kit.packages.mcp`. Single-entry
`a2kit.run(app)` dispatches all CLI / serve / schema / connections
modes from one console script.

### v1-cleanup-debt follow-ups (consolidated under v1.0)

- **`App.use_factory(factory, *, as_=stub)`** binds a factory under a
  stable callable identity. Replaces the legacy "module-level mutable
  slot" pattern in examples (`set_get_conn(...)` → `app.use_factory(...)`).
- **`compute_schema` canonical home** is `a2kit.packages.cli.schemas`.
  `a2kit.packages.testing.snapshots` re-exports it for the syrupy
  `TOONSnapshotExtension`.
- **`_APP_CTX`** lives in `a2kit.packages.cli.app_ctx`. Both adapters
  (`mcp.cli.serve_command`, `cli.builder.build_full_cli`) read from there.
- **`a2kit.packages.lint.static`** split — 1227 → 244 SLOC. Per-family
  rule modules under `a2kit.packages.lint.rules/`. **A2K010** (legacy
  unknown-atom rule) retired entirely.
- **CLI option synthesis** maps nullable primitives natively:
  `Optional[int]` / `int | None` → `INTEGER` (default `None`,
  `required=False`); same for `float`, `str`, `bool`. Non-primitive
  nullable types still JSON-decode.
- **Schema dump truncation**: `<app> schema [TOOL]` output now passes
  through `formatter.truncate(...)` (default 50,000-char cap).
- **ty (Astral)** is a hard `make lint` gate. `uv run ty check src/`
  exits 0 with zero `# ty: ignore` comments.
- **`opentelemetry` is lazy** — `import a2kit.packages.otel` does not
  pull `opentelemetry` into `sys.modules`; only `install(server)`
  triggers the load.
- **Test layout uniformity**: `tests/packages/select/` now has
  `__init__.py`; `pyproject.toml` sets `--import-mode=importlib` so
  test packages whose names shadow stdlib modules don't collide via
  `sys.modules`.

### New opt-in package

- `a2kit.packages.otel` — opt-in via `pip install 'a2kit[otel]'`. Adds
  an OTel-compatible `Middleware` that wraps every FastMCP tool call in
  a span (`mcp.tool.{tool_name}`) with attributes pulled from
  `A2KitMeta` (`a2kit.tool_name`, `a2kit.verb`, `a2kit.router`,
  `a2kit.tags`) plus the FastMCP request id, and increments an
  `a2kit.tool.calls{tool, verb, status}` counter. Wire with
  `from a2kit.packages.otel import install; install(server)`. a2kit
  core stays OTel-free; OpenTelemetry is lazy-imported.

### Migration recipes (populated as work lands)

- **CEL translation table** — legacy atom forms → CEL syntax (filled
  during Phase 2 `packages/select/`).
- **Import-path migrations** —
  - `from a2kit.di import Depends` → `from uncalled_for import Depends`
  - `from a2kit.contrib.connections import …` → `from a2kit.packages.connections import …`
  - `from a2kit.scaffold import Router` → `from a2kit import Router`
  - `from a2kit.testing import …` → `from a2kit.packages.testing import …`
  - `from a2kit.formatter import …` → `from a2kit.packages.formatter import …`
- **DI form** — `Annotated[T, Depends(g)]` → `T = Depends(g)`
  (parameter-default form via `uncalled_for`).
- **Connection contract** — `${VAR}` and `op://…` are now resolved
  **eagerly at `store.load(...)`**, not lazily at first tool call.
  Round-trip through `store.save(cfg)` preserves placeholders via the
  `_raw` shadow.
- **Override pattern** — `app.dependency_overrides[fn] = fake` →
  `make_test_app(routers, overrides={fn: fake})` from
  `a2kit.packages.testing`.
- **CLI entry** — `app.run()` → `a2kit.run(app)` (delegates to
  `a2kit.packages.cli.build_full_cli`).

### Install note

`toon-format` 1.0 has not yet shipped; v1.0 pins the working pre-release
exactly. If you bypass the pin (e.g. fresh resolve), pass `--pre`:

```
uv pip install --pre 'toon-format>=0.9.0b1'
```

### Risk-radius note

`uncalled-for` is pinned tightly (`>=0.3,<0.4`). It is pre-1.0 and
underpins every tool fn signature. If upstream introduces breaking
changes, expect a coordinated migration in the next a2kit release.

## 0.19.0.dev0 — 2026-05-08

**Fix-forward review pass on the v0.15 architecture.** No surface
changes; addresses two latent bugs and sweeps documentation drift.

### Latent bugs fixed

- **Multi-`ConnectionConfig` Depends params are now rejected at
  decoration time.** A tool declaring two `Annotated[T, Depends(...)]`
  params resolving to `ConnectionConfig` subclasses previously
  silent-picked the first one for `WriteEnforce` / OTel correlation.
  Raises `TypeError` with a clear message.
- **`connection=` shape now normalized through OTel / structlog.** A
  caller passing `connection=("p","e","d")` or
  `connection=["p","e","d"]` put the raw shape onto
  `ctx.state[STATE_CONNECTION_KEY]`, which then serialised
  inconsistently. Routed through `_resolve_connection_key` before
  stash so the span / log record always sees the canonical tuple form.

### Surface vestiges removed

- **`store=` parameter dropped end-to-end** from
  `Router.register_read` / `register_write`, the
  `_RegisterableRouter` Protocol, `Router._apply_bindings`, and
  `RouterRegistry.apply`. Routers stopped owning per-router stores in
  v0.15; this kept threading `store` through dead code paths.
  *Migration:* anyone with a hand-rolled Router implementing the
  structural `_RegisterableRouter` Protocol must drop the `store`
  parameter from `register_read` / `register_write` / `register_list`
  signatures. The framework no longer passes it.
- **`RouterRegistry.routers_with_stores(fallback_store=...)` →
  `ephemeral_store_pairs(store)`.** Renamed to spell out the actual
  purpose (the only consumer is the `--register` CLI path; nothing
  Router-owned).
- **`_CURRENT_RUNNER` ContextVar deleted** — only ever written, never
  read.

### Public API hardening

- **`App.get_store(conn_type) -> ConnectionStore[T]`** is the public
  store-lookup hook. Replaces `app._stores` private-attribute poking
  from `contrib/connections/_factory.get_conn_factory`. Match is
  exact-class identity, not `isinstance`.
  *Migration:* third-party contrib factories should replace
  ``next(s for s in app._stores if s.connection_class is T)`` with
  ``app.get_store(T)``. Subclasses of a registered conn type don't
  resolve to the parent's store — each class owns one store.

### Documentation drift

- Module docstrings rewritten for the v0.15+ surface
  (`a2kit/__init__.py`, `contrib/connections/__init__.py`,
  `contrib/connections/_helpers.py`, `tools/_connection.py`).
- **`a2kit.contrib.connections.make()` placeholder deleted** — it
  returned an unconsumed tuple and only existed as a syntax stub for
  an unbuilt SubApp surface. Migration note in `todo.md`.

### Tests

- Coverage stays at 100% (cov-fail-under=100 enforced).
- `tests/test_v19_latent_bugs.py` covers the two latent fixes.
- `tests/test_decorator_v15.py` listview / Passthrough assertions
  tightened (typed exception + Response shape).

## 0.18.0.dev0 — 2026-05-08

**Structured tool logging.** Adds `a2kit.get_tool_logger(name)` — a
structlog `BoundLogger` that shares the same `tool.name` /
`tool.connection` labels the OTel span carries, by reading them from
`structlog.contextvars`. A new logging middleware binds those keys for
the duration of each tool call (both async-chain and sync `@tool`
paths), so any log emitted from the tool body, plugin code, or
downstream middleware inherits the labels. Concurrent tool calls stay
isolated (per-task contextvars).

What's *not* in scope: trace_id/span_id injection into log records.
The kit binds labels only — for full trace correlation, hosts bridge
structlog→stdlib logging and enable OTel `LoggingInstrumentor`
themselves. The kit ships **no** structlog *configuration*
(processors, formatter, handler) for the same reason. structlog
imports are lazy.

(Plan-vs-impl note: the v0.17 ledger called the type a "structlog
`LoggerAdapter`" — that was a stdlib/structlog conflation. structlog's
`BoundLogger` is the actual contextvar-aware shape and is what shipped.)

`structlog>=24` added to runtime dependencies.

### FastMCP request-id spike — closed

Investigation: `Context.request_id` exists on FastMCP's Context but is
only injected when the tool declares a `Context`-typed kwarg.
Stamping it as `mcp.request_id` on the span would force a2kit to
import `mcp.server.fastmcp.Context` at runtime — contradicting the
v0.11 `FastMCPLike` Protocol design. Closed; finding + follow-up paths
captured in `todo.md`.

## 0.17.0.dev0 — 2026-05-08

**Hygiene.** v0.17 audits the pre-v0.13 P1/P2/P3 backlog (most items
turned out stale or already-landed), executes the surviving real items
(formatter robustness + Hypothesis property tests + OTel
`tool.result.count`), and deletes the v0.16 `ConnectionInfo` alias.

### Backlog audit

`todo.md` P1/P2/P3 sections (lines 26-72, captured pre-v0.13) honest
again — every item is checked, struck stale, or surviving-and-current.
The v0.13–v0.15 surface deletes invalidated most P3 items
(`tools.py`, `_RouterContext`, `MCPRunner.store=`, `_auto_inject_enabled`,
typed-info DI all gone). The async store API, `MCPRunner.run_async`,
`EnricherFn` async support, and OTel `record_exception` already landed
in v0.11–v0.13.

### Formatter robustness (P1)

- **`_dump_items` raises on non-row items** instead of silently dropping
  them. Pre-v0.17 behaviour turned `[1, 2, 3]` into `[]`, masking
  row-shape bugs. `format_response` gates the call to only normalize
  when `data[0]` is a `dict` / `BaseModel`; heterogeneous lists now
  fall through to the JSON path.
- **`format_from_annotation` unwraps `Awaitable[T]` / `Coroutine[Y, S, T]`**
  before classifying — async tools no longer lose precomputation.
- **Bare `dict`, `Mapping[K, V]`, `TypedDict` subclasses** classify as
  `"json"` (previously fell through to `None`).
- **`_flat_pydantic_fields` handles multi-arm `Optional[Union[A, B]]`**.
  Previously only single-arm Optional was unwrapped; multi-arm fell
  through. New `_classify_arm` helper inspects each non-None arm.

### OTel observability (P2)

- **`tool.result.count` span attribute** — stamped by the OTel
  middleware when the tool returns `list` / `tuple` / `Page[T]`.
  Cardinality only — PII-safe and stamped after success only
  (meaningless on error).

### Property tests (Hypothesis)

- `truncate(value)` is structural identity at high `max_chars` and
  never mutates input — verified against a recursive value strategy
  (atoms / lists / dicts up to depth 4).
- `format_from_annotation(list[FlatModel])` precompute agrees with
  `toon_or_json` runtime classification.
- `hypothesis>=6` added to dev deps; 25 new tests in
  `tests/test_v17.py`.

### Deleted: `ConnectionInfo` alias

v0.16 added `ConnectionInfo = ConnectionConfig` as a one-cycle alias
with an explicit "delete in v0.17" plan. Done.
`src/a2kit/lint/_ast_helpers.py` no longer recognises the old name;
all tests + the tracker example use `ConnectionConfig` directly.
`ConnectionInfoLike` Protocol stays — it's a structural type and the
rename pressure doesn't apply.

### Tests

- 589 tests (564 → 589), 100% coverage.
- `make lint && uv run pytest -q && make examples` green.

## 0.16.0.dev0 — 2026-05-08

**Polish.** v0.16 closes the v0.15 coverage drop, renames the
long-deprecated `ConnectionInfo` → `ConnectionConfig`, and scrubs the
README of stale `Plugin` / `Provider` / `store=` references.

### Coverage refill: 80% → 100%

- ~290 focused tests in `tests/test_v16_coverage.py` covering the
  formatter decision tree, lint AST helpers + rule branches, `app.py`
  CLI body, projection / `_otel` / signature splicing, scaffold runner
  pyproject loaders, `ConnectionStore` edge cases, and enricher
  sync/async drain.
- `cov-fail-under` bumped back to `100` in `pyproject.toml`.
- A handful of genuinely-defensive branches got `pragma: no cover`
  (the optional celpy ImportError, the OTel real-provider fallback,
  the 3rd-tier anyio drain in `apply_enricher_sync`, a few rare
  branches in `_compute_tool_capabilities`).

### `ConnectionInfo` → `ConnectionConfig`

The class lives in `src/a2kit/connections.py` and is now
`ConnectionConfig`. `ConnectionInfo` remains as a module-level alias
for one cycle (removed in v0.17). All internal references — TypeVars,
contrib factory, scaffold CLI/stores, lint helper base-class
string-match — updated. The lint AST helper recognises both names so
user code on the alias still satisfies A2K003 / A2K012 detection.

### README scrub

- Status header rewritten to describe the v0.16 surface (was v0.13).
- API surface table adds `App`, `Depends`, `get_conn_factory`, the
  verb decorators (`@a2kit.read` / `@a2kit.write` / `@a2kit.list`).
- "How a new MCP starts here" walkthrough rewritten around `App` +
  `Annotated[ConnT, Depends(get_conn)]`.
- All v0.7-v0.12 migration footnotes (`*, info: ConnT`,
  `connection_param=`, `Router.store=`, `MCPRunner.store=`,
  `Plugin`/`PluginBase`/`Provider`) collapsed into a CHANGELOG
  pointer.
- `MCPRunner(server, store=store)` examples updated to the v0.15
  `connection_store=` kwarg name.

### Tests

- 564 tests, 100% coverage.

## 0.15.0.dev0 — 2026-05-08

**The big delete.** v0.15 collapses two years of v0.7→v0.12 connection-DI
vocabulary into the single `Annotated[T, Depends(factory)]` idiom. Breaking
compat; no deprecation footnotes.

### New surface

- **`a2kit.contrib.connections.get_conn_factory(app, ConnT)`** — the
  canonical Annotated/Depends factory for connection injection. Returns
  a callable matching the `Depends(...)` factory shape (declares
  `connection: str` as a kwonly so the resolver forwards the call-site
  value). Tests override via `app.dependency_overrides[get_conn] = fake`.
- **WriteEnforce middleware wired automatically.** Tools decorated with
  `@write` (or `write=True`) get the `write_enforce_factory()` middleware
  in their implicit chain — read-only connections raise `WriteNotAllowed`
  before the tool body runs.
- **Transitive `connection` kwarg surfacing.** When a tool declares
  `Annotated[Store, Depends(get_store)]` and `get_store` depends on
  `Annotated[Conn, Depends(get_conn)]`, the wrapper walks the chain and
  exposes `connection: str` on the published signature.

### Removed (breaking)

Tool decorator:

- `connection_param=` kwarg.
- Typed-info DI autodetect (`*, info: ConnT`); `_detect_info_param` helper.
- `store=`, `connection=`, `resolver_registry=`, `router_context=` kwargs.
- Connection-aware branches in `_prelude` / `_prelude_async`. Async
  prelude is now 16 LOC — only `tool_call_guard` remains.

DI container (`a2kit.di`):

- `Provider`, `Plugin`, `PluginBase`, `Binding`, `ToolPlan`.
- `ProviderCollisionError`, `ProviderCycleError`,
  `UnknownProviderTypeError`, `UnknownProviderDepError`.
- `resolve_chain`, `_validate_provider_graph`, `_provider_dep_types`.

Runner:

- `provides=` and `plugins=` kwargs.
- `store=` kwarg → `connection_store=`; public `MCPRunner.store`
  attribute is now private `_connection_store`.
- `lookup_provider`, `resolve`, `cli_commands`.

App:

- `App.use(Plugin)` / `App.use(Provider)` arms.

Router:

- `Generic[ConnT]` parameterisation.
- `store`, `resolver_registry`, `ephemeral`, `auto_connection_enricher`
  fields.
- `Router.context` ClassVar + `_RouterContext` (`_context.py` removed).

Lint:

- A2K001, A2K004. Both checked features that no longer exist.

Misc:

- `_safe_list_connection_keys` (decoration-time saved-key listing).

### Tests

- 11 version-stamped legacy test files deleted (~5800 LOC):
  `test_v03/v031/v04/v06/v07/v08/v10/v11/v12.py`, `test_tools_fat.py`,
  `test_exceptions_v02.py`.
- Added: `tests/test_app_use.py` and `tests/test_decorator_v15.py` cover
  Annotated/Depends end-to-end (saved-conn round-trip, overrides,
  transitive deps, WriteEnforce, CLI shape).
- Final: 290 tests, 80% coverage. `cov-fail-under` temporarily relaxed
  to 0; deferred 100% restoration to v0.16.

### Migration

```python
# v0.14
@MyRouter.read()
async def list_them(*, conn: TrackerConn) -> list[dict]: ...
```

```python
# v0.15
from typing import Annotated
from a2kit.di import Depends
from a2kit.contrib.connections import get_conn_factory

app = a2kit.App("tracker")
app.connect(TrackerConn)
get_conn = get_conn_factory(app, TrackerConn)

@MyRouter.read()
async def list_them(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[dict]: ...
```

`examples/tracker/` is the canonical reference; `examples/tracker/deps.py`
shows the slot pattern that keeps routers decoupled from the `App` instance.

## 0.14.0.dev0 — 2026-05-08

**Polish turn (in progress).** v0.14 picks up the v0.13 deferred backlog;
this dev cut lands two cleanup commits and adds App-scope enricher
plumbing. The big v0.12 connection-surface deletion (`Router.store`,
`MCPRunner.store=`, `connection_param=`, `_detect_info_param`,
`Plugin`/`PluginBase` Protocols, `Router(BaseModel, Generic[ConnT])`)
remains carried over and is the next shaping target — see `todo.md` for
the v0.14 ledger.

### New surface

- **`App(name, enricher=...)`** — App-scope enricher fallback. Resolution
  order at the binding layer is `tool > router > app`, with the existing
  `auto_connection_enricher(store)` as the implicit floor. Routers
  without their own `enricher=` inherit the app's at apply time.

### Removed

- **A2K005** lint rule (`KEY_FIELDS` migration aid + `cls.Key` arity
  cross-check). Carried since v0.5; the legacy `KEY_FIELDS` syntax is
  long gone. Drops `key_fields_value`, `connection_info_key_class`,
  `namedtuple_field_count`, `connection_info_subclasses` AST helpers
  alongside it. ~800 lines net deletion (src + tests + docs).

### Deferred to v0.15

- **`ConnectionInfo` → `ConnectionConfig` rename** — Pydantic schema
  name + error-message ripple across the test corpus exceeded session
  budget; documented for next cycle.
- **Hard delete of the v0.12 connection surface** (the headliner). All
  nine items (`Router.store`, `MCPRunner.store=`, `connection_param=`,
  `_detect_info_param`/`info_target`, `_prelude_async` connection
  branch, `Router(BaseModel, Generic[ConnT])` TypeVar, `Plugin` /
  `PluginBase` Protocols, `Provider` Protocol, `App.use()`'s Plugin
  arm) are interlocked with ~117 `connection_param=` test sites and
  31 `Plugin`/`PluginBase` references; doing them as one coordinated
  migration is its own multi-session pitch.
- **`SubApp` / `app.mount(...)` shape + `connections.make()` real
  SubApp.** Parked behind the surface deletion above.
- **`PLC0415` per-file ignore in `tests/**`.** 123 hits across the
  test corpus; non-trivial migration left for a focused commit.

## 0.13.0 — 2026-05-08

**Library-swap turn + middleware split.** Replaces three bespoke modules
with their stdlib / OTel / vcrpy equivalents, introduces `Annotated[T,
Depends]` DI alongside the v0.12 `provides=` path, splits the fat tool
decorator into a middleware chain, and lifts connection-aware logic into
`a2kit.contrib.connections` so the core decorator no longer knows what a
ConnectionInfo is.

### New surface

- **`Annotated[T, Depends(factory)]` DI** — FastAPI/FastMCP idiom for
  per-tool typed dependencies. `*, store: Annotated[TodoStore,
  Depends(get_todo_store)]` resolves at call time with per-call caching
  and cycle detection, validated at decoration.
  `app.dependency_overrides[get_conn] = fake` swaps factories in tests.
- **`Depends(factory)`** — frozen dataclass marker re-exported from the
  top-level `a2kit` namespace. Lives next to the v0.12 `Provider`
  Protocol; pick the shape that fits the call site.
- **Implicit middleware chain** (`a2kit.middleware`) — the tool decorator
  now assembles a Starlette-style chain at decoration time:
  `tool_call_guard` → `capability_guard` → `otel_span` (always); plus
  `write_enforce`, `list_view_apply`, and `enrich_errors` only when the
  verb / Router / connection asks for them. Authors keep writing
  `@MyRouter.write()` — the chain is implicit. Hooks for
  `@MyRouter.write(middleware=[mw])`, `Router.middleware = [...]`, and
  `App.middleware = [...]` exist for the rare tier-3 case.
- **`a2kit.contrib.connections`** — connection-aware helpers
  (`lookup_connection_async`, `resolve_connection_key`,
  `resolve_info_strings`, `write_enforce_factory`) live in their own
  contrib package. The v0.13 plan ("pull connections out of core") is
  partially landed — re-exports keep v0.12 paths working; v0.14 deletes
  the legacy paths and finishes the SubApp / `connections register`
  CLI subcommand work.
- **`RunnerOptions`** — typed dataclass for `MCPRunner.run(options=...)`.
  Replaces argv-string round-tripping in `App.cli`'s `serve` subcommand;
  `argv=` stays as a v0.12 compat layer.

### Library swaps

| Concern | Before | After |
|---|---|---|
| Sync→async drainage | `a2kit._async_bridge` (18 LOC) | `anyio.from_thread.run` direct |
| OTel NoOp fallback | `_otel.py._NullSpan` (~150 LOC) | `opentelemetry.trace.NoOpTracer` |
| VCR cassettes | `_cassette.py._make_async_ctx` (~40 LOC) | `vcrpy` direct |

Net delete: ~200 LOC of bespoke wrappers that re-implemented stdlib /
upstream-library shapes.

### Deferred to v0.14

- **`_select*.py` → `cel-python`.** Probed; structural blockers in
  user-facing grammar (`and`/`or` vs `&&`/`||`, atom keys with dots)
  and the `SelectExpr` AST consumed by lint rules and scaffold
  introspection (~100 references). Re-open as a dedicated pitch.
- **`tokens.py` → `pydantic-settings` + `pyonepassword`.** Mismatched
  abstractions (`resolve_env` substitutes inside arbitrary strings;
  `pydantic-settings` is a typed settings-model loader); zero-LOC
  savings on the op:// side.
- **Core deletes that touched 30+ test sites.** `Router.store`,
  `MCPRunner.store=`, `connection_param=`, the `_prelude_async`
  connection branch, `_detect_info_param` / `info_target` plumbing,
  `Router(BaseModel, Generic[ConnT])`, and the `Plugin` / `PluginBase`
  Protocols all stay as v0.12-compat surfaces. v0.14 will migrate the
  test corpus to `Annotated[Conn, Depends(get_conn)]` then delete the
  compat code in one pass.
- **`PLC0415` removal from `tests/**`.** The audit halved the noqas in
  `src/` (49 → 25); the remaining 25 are genuine optional-dep / circular
  / verb-decorator factory cases. The test corpus has 123 PLC0415 hits —
  non-trivial migration deferred.

### Coverage

Restored to **100%** (`cov-fail-under=100`). The two v0.12 holes
(`enrichers.py:108`, `tools/_signature.py:113`) plus three drive-by
gaps from the middleware split now have direct tests.

## 0.11.0 — 2026-05-08 (in progress)

**Contract-clarity turn.** Tightens the public vocabulary, restores type
safety on the most-used classes, and exposes a stable accessor for tool
metadata. No new behaviour — the engine is untouched. Existing v0.10 tools
keep working without changes.

### New

- **`a2kit.enrichers`** is the canonical home for `EnricherFn`,
  `chain(*fns)`, and `connection_enricher(store)`. The previous module
  `a2kit.errors` is now a deprecation shim that re-exports from `enrichers`
  and warns at import. Scheduled for removal in **v0.13**. Update imports:
  `from a2kit.enrichers import ...`. The clarification: `a2kit.exceptions`
  holds exception *classes*, `a2kit.enrichers` holds enrichment *functions*.
- **`ConnectionInfoLike` / `ConnectionStoreLike`** moved to their natural
  home `a2kit.connections` (still re-exported from the deprecated
  `a2kit.errors` for one cycle, and from the top-level `a2kit` namespace).
- **`FastMCPLike` Protocol** in `a2kit.scaffold` — the minimum FastMCP server
  surface `MCPRunner` drives (`tool()`, `run()`, `settings`). Use it to type
  your own server wrappers / mocks. Runtime-checkable.
- **`tool_metadata(fn)` → `ToolMetadata`** — public, frozen, slotted accessor
  for the kit-stamped `_a2kit_*` attrs (`tool_name`, `capabilities`,
  `format`). Tests and consumers should assert against `ToolMetadata`, not
  the underlying private attributes.

### Changed (typing — no runtime behaviour change)

- `Router.store / .enricher / .resolver_registry / .ephemeral` are now
  typed (`ConnectionStoreLike | None`, `EnricherFn | None`,
  `ResolverRegistry | None`, `Mapping[tuple[str, ...], ConnectionInfo] | None`)
  instead of `Any`. Pydantic still accepts these — `arbitrary_types_allowed=True`
  was already set — but ty / IDEs now see the real shape on every consumer.
- `MCPRunner.__init__(server, store=...)` accepts `FastMCPLike` and
  `ConnectionStore[Any] | None` instead of `Any`.
- `RouterRegistry._routers` entries are now `_RouterEntry` NamedTuples
  instead of bare 3-tuples — internal cleanup, no API change.
- `Page[T]` docstring locks the convention: `T` is `BaseModel` (preferred —
  enables tsv/toon precompute) or `dict[str, Any]` (ad-hoc rows). The
  TypeVar bound is left off because Pydantic v2 generic-bound interplay
  with `Page[dict[...]]` is fragile.
- `next_cursor` documented as an opaque agent-only string (the kit never
  parses or interprets it).

### Removed

- **`a2kit.A2KIT_CONFIG_HOME`** — was a self-alias for `ENV_CONFIG_HOME`.
  Use `a2kit.ENV_CONFIG_HOME` instead. `a2kit.A2KIT_CONFIG_HOME` now raises
  `ImportError` with a migration hint.

### Deprecated

- **`a2kit.errors` module** — emits `DeprecationWarning` at import. Removed
  in v0.13.

### Compatibility

- All v0.10 tests pass unchanged. 618 tests, 100% coverage, ruff + ty clean.
- Test fakes for `FastMCPLike`-typed args may need to add a `tool()` method
  if they didn't have one (most fixtures already do for FastMCP parity).

## 0.10.0 — 2026-05-07

**Surface-simplification turn.** Four targeted wins, all additive over v0.9:
the wire format is decided at decoration time when possible, `Page[T]` of
Pydantic models actually serialises to TSV/TOON, every Router with a store
gets the typo-suggestion enricher for free, and the agent-facing
`connection: str` schema lists the saved keys it knows about.

### New

- **Format-from-type at decoration time.** When the tool's return type is
  concrete (`list[Issue]`, `Page[Issue]`, `dict`, `Issue`, `int`, …), the kit
  precomputes the wire format (`tsv` / `toon` / `json`) once. Each call skips
  the runtime list-of-dicts walk. Stamped on the wrapper as `_a2kit_format`.

  Decision tree:
  - `list[T]` / `Page[T]` where `T` is a Pydantic model with all-flat
    fields → `tsv` locked.
  - Same shape with at least one `list` / `dict` / nested-Pydantic field →
    `toon` locked.
  - Single `dict`, single Pydantic model, scalar return, `None` → `json` locked.
  - Untyped `list`, `list[dict]`, `Any`, unresolvable forward ref → `None`
    (runtime fallback, identical to v0.9 behaviour).

- **`Page[T]` with Pydantic items.** `_dump_items()` flattens
  `Page[Issue].items` via `model_dump()` before the tabular encoder sees
  them, so `Page[Pydantic]` returns a real TSV/TOON payload instead of
  `str(Issue)` slop. Same fix applies to `list[Pydantic]`.

- **Auto-wired `connection_enricher` on Routers with a store.** A typo in
  the `connection` arg now returns

  ```
  Connection not found: prdo
  Available: prod, staging
  Did you mean: prod?
  ```

  …without the author wiring `enricher=connection_enricher(self.store)`.
  Disable with `auto_connection_enricher=False` on the Router subclass; an
  explicit `enricher=` still wins.

- **Schema enrichment for `connection: str`.** The injected docstring
  inlines the saved connection keys (`Currently saved: 'prod', 'staging'`)
  so the agent sees valid values inline instead of having to call
  `connections list` out-of-band. Empty stores fall back to the v0.9
  generic phrasing.

### Changed

- `format_response(...)` accepts `format_hint: FormatName | None` (default
  `None`). Hint is trusted unless the data shape is incompatible (e.g.
  `tsv` hint on a single dict → falls back to JSON).
- `connection_enricher(store)` parameter type relaxed from
  `ConnectionStore[ConnectionInfo]` to `Any` — the function only needs
  `.list_connections()`. Lets the router's internal `_EphemeralAwareStore`
  proxy flow through without `cast()`.

### Migration from 0.9

No breaking changes. `connection_param=` is still a soft-deprecated alias
(slated for v0.11). Three opt-out hooks:

- Router auto-enricher: `class WidgetsRouter(Router): auto_connection_enricher = False`
- Schema-key enrichment: not configurable in v0.10 — keys are listed when
  `store.list_connections()` succeeds and yields ≥ 1 entry.
- Format-from-type: omit the return annotation, or annotate with `list[dict]` /
  `Any` to force the runtime path.

## 0.9.0 — 2026-05-07

**Ergonomic overhaul.** Pre-1.0, no users — clean breaks across error
handling, capability declarations, list-view tools, and the connection-key
contract. Most tool signatures get shorter; the agent-facing schema gets
sharper; the kit's mental model collapses by one layer.

### New

- **`@Router.read()` / `@Router.write()` auto-inject `connection: str`** into
  the agent-facing schema whenever the Router has a store. Authors stop
  writing `connection_param="conn"` and stop adding `conn: str` to their fn
  signature.

- **Type-driven info DI** — declare a `ConnectionInfo`-subclass typed
  parameter on your fn (`info: WidgetConn`); the kit binds the resolved info
  there at call time. Hidden from the agent-facing schema. `Router.context.info()`
  survives as the helper-function escape hatch:

  ```python
  @WidgetsRouter.read()                                  # zero kwargs
  async def list_widgets(info: WidgetConn) -> list[dict]:
      return [{"url": info.url}]
  # Agent calls list_widgets(connection="prod"); kit resolves + injects info.
  ```

- **List-view triad** — three orthogonal flags, two execution modes each:

  | Concern    | Local (kit handles)               | Passthrough (tool handles)              |
  |------------|-----------------------------------|------------------------------------------|
  | `filter`   | CEL post-process on rows          | thread `filter:str` to fn (compile to JQL/SQL/…) |
  | `fields`   | dict-key projection on rows       | thread `fields:list[str]` to fn          |
  | `pagination` | slice + opaque cursor encoding | thread `limit:int, cursor:str|None` to fn; tool returns `Page[T]` |

  Replaces v0.8's `projection=True` / `cel_filter_param=` / `fields_param=`
  with a coherent execution-mode story so MCPs that pushdown filtering or
  pagination upstream (a2db SQL, a2atlassian JQL) get first-class support
  alongside in-memory data sources (Reddit JSON, local lists).

- **`Page[T]`** — typed Pydantic generic for tools that own pagination
  upstream. `items: list[T]`, `next_cursor: str | None`. Kit unwraps and
  threads `next_cursor` into the outer `Response`.

- **Output formats split honestly: `tsv` vs `toon`** — flat rows render as
  TSV (header + tab-separated scalar cells); rows with at least one nested
  value render as TOON (same shape, but nested cells are compact-JSON-encoded
  inline). `Response.format` is now `Literal['tsv', 'toon', 'json']`. The
  v0.8 'toon' label was lying about the encoding.

- **`Router.capabilities` is `ClassVar`** — caps describe the router's *type*,
  not its runtime instance. Mirrors the existing `read_capabilities` /
  `write_capabilities` `ClassVar` pattern.

  ```python
  class IssuesRouter(a2kit.Router):
      capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}
  ```

- **Errors simplified — `EnricherFn = Callable[[Exception, str | None], Exception]`**
  replaces `ErrorEnricher` Protocol + `EnricherRegistry`. Composition via a
  6-line `chain(*fns)` helper. `connection_enricher(store)` factory replaces
  the `ConnectionNotFoundEnricher` class — closes over the store, returns a
  plain function.

  ```python
  @a2kit.tool(enricher=chain(my_enricher, connection_enricher(store)))
  async def query(...): ...
  ```

### Breaking

- `xml_guard` already renamed to `tool_call_guard` in v0.8 — this remains.
- **`projection=True`, `cel_filter_param=`, `fields_param=` removed.** Use
  `filter=Local|Passthrough`, `fields=Local|Passthrough`,
  `pagination=Local|Passthrough` instead.
- **`ErrorEnricher` Protocol, `EnricherRegistry`, `ConnectionNotFoundEnricher`
  class removed.** Use `EnricherFn` callables, `chain(*fns)`,
  `connection_enricher(store)` factory.
- **`ToolConfig` Pydantic model removed.** It was never wired to the live
  decorator — the authoritative kwarg contract is the `ToolKwargs` TypedDict.
- **`Router.capabilities` as a Pydantic instance field is gone.** Move to
  `ClassVar[set[Capability]]` on the subclass.
- **`Response.format` widened to `Literal['tsv', 'toon', 'json']`.** Existing
  `format == "toon"` assertions on flat data will return `"tsv"` instead.

### Soft-deprecated (drops in v0.10)

- **`connection_param=<name>` kwarg** still works as a back-compat alias for
  the v0.8 string-named connection lookup. New code should use the typed-info
  DI pattern (`info: <ConnectionInfo subclass>`).

### Internal

- 561 tests, 100% line+branch coverage, lint + ty clean.
- Examples still 5 files; example 03 renamed `03_projection_tool.py` → `03_list_view.py`
  and rewritten to demonstrate Local + Passthrough side-by-side.

## 0.8.0 — 2026-05-07

**Polish bundle.** Pre-1.0 cleanups surfaced after v0.7: rename
`xml_guard` → `tool_call_guard`, lift ephemeral handling out of the tool
decorator, type-tighten `Router.tool/.read/.write` signatures, type-promote
`format_response`, and add a `projection=True` ergonomic shortcut.

### New

- **`@a2kit.tool(projection=True)`** — auto-injects `filter: str` and
  `fields: list[str] | None` keyword-only params into the wrapper signature
  (FastMCP's tool schema picks them up; agents call with them) and post-processes
  the result through `format_response`. Authors no longer write any projection
  plumbing for the common case:

  ```python
  @a2kit.tool(projection=True)
  def list_widgets() -> list[dict]:
      """Return widgets."""
      return _WIDGETS
  ```

  Collisions with author-declared `filter`/`fields` params raise at decoration
  time. The explicit `cel_filter_param=`/`fields_param=` path remains as a
  power-user escape hatch and cannot combine with `projection=True`.

- **`a2kit.Response`** — typed Pydantic envelope returned by `format_response`.
  Fields: `format` (`Literal["toon", "json"]`), `data` (`str`), `truncated`
  (`bool`), `next_cursor` (`str | None`, reserved for v0.9 pagination). Frozen,
  `extra="forbid"`.

- **`Router.tool/.read/.write` signatures use `Unpack[ToolKwargs]`.** Authors
  composing higher-order Router classmethods now get end-to-end type-checking
  on the kwarg contract.

### Breaking

- **`xml_guard` → `tool_call_guard`** on `@a2kit.tool(...)`, `ToolConfig`, and
  the public `ToolKwargs` TypedDict. Same behaviour, less misleading name —
  the guard refuses any `str` arg containing `<parameter name=` (tool-call
  envelope contamination from agents), and that's a tool-call concern, not
  XML in the abstract.

- **`ToolXMLContamination` → `ToolCallContamination`.** Same shape, same
  message; renamed for symmetry with the kwarg.

- **`format_response` returns `Response`, not `dict`.** Migration: replace
  `env["format"]` with `env.format`, etc.

- **`ephemeral=` removed from public `@a2kit.tool` kwargs** and from the public
  `ToolKwargs` TypedDict. Ephemeral connections live at the Router level only —
  `Router(..., ephemeral={...})` works unchanged. Internally,
  `Router._apply_bindings` now wraps the effective store in a private
  `_EphemeralAwareStore` proxy so the tool decorator never thinks about
  ephemeral connections. Tools that previously passed `ephemeral=` directly to
  the decorator should construct an `_EphemeralAwareStore` explicitly or use a
  Router.

### Internal

- 556 tests, 100% line+branch coverage on 2224 statements / 832 branches.
  No changes to the linter pack, scaffold CLI, or runtime introspection seams.

## 0.7.0 — 2026-05-07

**Idiomatic Python pass.** Pre-1.0 cleanups: idiomatic `StrEnum Cap`, removal of
the `info` kwarg shape, auto-injected param docs, public `ToolKwargs`, FQN
ContextVar naming, A2K012 hardening, A2K013 added.

### New

- **`Cap` is a `StrEnum`.** `list(Cap)` enumerates all members; `Cap("write")`
  parses a raw string; `Cap.WRITE == "write"` is True; Pydantic v2 native
  serialization. The capability registry pre-registers built-ins via the same
  `capabilities.register(...)` path; lib code never branches on cap names.
- **Auto-inject param docs.** When a tool function has `connection_param="conn"`,
  the canonical `connection_param_doc(...)` text is prepended to the docstring
  at decoration time. Same for any `register_param_doc(name, text)` entry whose
  name matches a function parameter. Configurable via
  `[tool.a2kit.docs] auto_inject = false`.
- **A2K013** (advisory) — flags tool docstrings that still call
  `a2kit.docs.connection_param_doc(...)` / `param_doc(...)` via f-string;
  auto-injection covers it.
- **Public `ToolKwargs` TypedDict.** Use `Unpack[ToolKwargs]` for higher-order
  Router classmethod factories (e.g. a custom `expensive` decorator that
  defaults `Cap.EXPENSIVE`). New example: `examples/higher_order_decorator.py`.
- **A2K012 re-export resolution.** A2K012 now follows `from pkg import NAME`
  through `pkg/__init__.py` re-exports (cap depth 3) to confirm the constant
  terminates at a `Final[str]` annotation. Re-exports without a `Final[str]`
  terminus are flagged.

### Breaking

- **`info_kwarg` removed from `@a2kit.tool(...)`.** The kwarg-injection path
  (`*, info: ConnT | None = None`) is gone; the only supported access is
  `Router.context.info()`. `ToolConfig.info_kwarg` field also removed.
  Migration:

  ```python
  # Before:
  async def get_widget(conn: str, *, info: WidgetConn | None = None) -> dict:
      return {"url": info.base_url}

  # After:
  async def get_widget(conn: str) -> dict:
      info = WidgetsRouter.context.info()
      return {"url": info.base_url}
  ```

- **`Cap` is no longer a plain class with `Final[str]` constants.** Author
  syntax `Cap.WRITE`, `Cap.READ`, etc. is unchanged (StrEnum subclasses `str`,
  same equality semantics, same set/dict membership). The only observable
  difference: `Cap.WRITE.value == "write"` exposes the underlying string, and
  `repr(Cap.WRITE)` now shows `<Cap.WRITE: 'write'>`.

### Bug fixes

- **FQN-based `_RouterContext` ContextVar naming.** Two same-named Router
  classes in different modules (e.g. `app/jira/IssuesRouter` and
  `app/github/IssuesRouter`) used to share a ContextVar by `cls.__name__` and
  collide. v0.7 names the ContextVar with `f"{cls.__module__}.{cls.__qualname__}"`,
  giving each Router class independent state. Transparent rename — no author
  change needed.

### Examples

- **NEW** `examples/v07_minimal_mcp.py` (replaces `v06_minimal_mcp.py`) —
  StrEnum Cap demo + ContextVar-only flow.
- **NEW** `examples/higher_order_decorator.py` — `Unpack[ToolKwargs]` factory.
- **UPDATED** `examples/fat_tool.py`, `examples/router_class.py`,
  `examples/v03_minimal_mcp.py` — drop `info` kwarg, use ContextVar.

## 0.6.0 — 2026-05-07

**Router ergonomics + DI + type-verification + capability unification.** Additive
on top of v0.5.0; no destructive changes to v0.5 callers.

### New

- **Auto-derived Router names.** `class WidgetsRouter(a2kit.Router)` now slugs
  to `name="widgets"` automatically. `JiraConfluenceRouter` → `jira-confluence`.
  Explicit `name="..."` still wins.
- **`@MyRouter.read` / `.write` / `.tool` classmethod decorators.** Bind tools
  declaratively at module scope; `register_read` / `register_write` walk
  `cls._tools` by default. Each subclass gets its own fresh `_tools` list via
  `__init_subclass__` to avoid the mutable-default trap. Imperative override
  is still supported as the documented escape hatch (D).
- **Router-level DI.** Lift `store`, `enricher`, `resolver_registry`,
  `ephemeral` to the Router instance; every tool inherits. Per-tool decorator
  kwargs override.
- **`MyRouter.context.info()` typed accessor.** Each Router subclass gets a
  per-Router `_RouterContext` ClassVar backed by a `ContextVar`. The fat
  `@a2kit.tool` decorator sets it before the wrapped fn runs and resets after.
  The `*, info: ConnT` kwarg style still works in parallel and is opt-in
  (only injected if the function declares the kwarg or `**kwargs`).
- **Multi-store MCPs.** `Router(store=...)` per-router; `MCPRunner` aggregates
  via `RouterRegistry.routers_with_stores()`. CLI uses `--register router:key=...`
  namespaced parsing when >1 distinct store is registered; bare form raises
  with router-prefix suggestions.
- **A2K012 lint rule.** Advisory: raw-string custom capability that isn't a
  built-in `Cap.*` constant and isn't an imported / local `Final[str]` constant.
  Skipped on `tests/` and `examples/`.
- **Capability unification reframe.** Built-ins are pre-registered via the same
  `capabilities.register(...)` path as custom caps; `Cap` is a typed
  convenience reference (no special-casing in lib code). A2K009 stays as
  advisory for the built-in case.

### Breaking

- None for the v0.5 API surface. The `register_read` / `register_write`
  methods still exist; they now have a default implementation that walks
  `cls._tools`. Authors who override imperatively continue to work unchanged.

### Migration recipes

```python
# v0.5 — register_read with manual @a2kit.tool:
class WidgetsRouter(a2kit.Router):
    def register_read(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="conn")
        async def list_widgets(conn: str, *, info) -> list[dict]:
            return [{"url": info.url}]

# v0.6 — declarative + typed context:
class WidgetsRouter(a2kit.Router):
    pass

@WidgetsRouter.read(connection_param="conn")
async def list_widgets(conn: str) -> list[dict]:
    info = WidgetsRouter.context.info()  # typed
    return [{"url": info.url}]

routers.add(WidgetsRouter(store=store))
```

## 0.5.0 — 2026-05-07

**Breaking change.** `KEY_FIELDS: ClassVar[tuple[str, ...]]` is removed in favour
of a NamedTuple-based `Key` class declared via `key=` on the subclass. This
unlocks per-field types (e.g. `env: Literal["dev", "staging", "prod"]`),
keeps NamedTuple-as-tuple compatibility for the existing positional/tuple/kwargs
load shapes, and adds a fully-typed `store.load(WidgetKey(...))` shape.

**Migration recipe:**

```python
# Before (v0.4):
class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")

# After (v0.5):
from typing import NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str

class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    ...
```

Subclasses that still declare `KEY_FIELDS` raise `MigrationRequired` at class
creation time with a generated migration snippet. (Pre-1.0 clean cut: no alias,
no warning grace period.)

**New**

- `ConnectionInfo.__init_subclass__` accepts `key=<NamedTupleClass>`. The class
  is bound as `cls.Key`. Default is the built-in `_DefaultKey(name: str)`.
- `ConnectionStore.load()` accepts a NamedTuple instance directly as a
  fifth call shape: `store.load(WidgetKey(project="a", env="dev", db="c"))`.
  All previous shapes (kwargs / tuple / list / positional / bare-string) still work.
- `ConnectionStore.key_class` property — exposes `model.Key`.
- `ConnectionStore.list_keys()` — returns typed NamedTuple instances rather
  than raw `tuple[str, ...]`. Existing index-style access still works.
- New exception: `MigrationRequired`.
- Examples: `examples/typed_key_literal.py` (per-field `Literal` typing),
  renamed `examples/key_namedtuple.py` (was `key_fields.py`),
  renamed `examples/v05_minimal_mcp.py` (was `v04_minimal_mcp.py`).

**Behavioural changes**

- `KeyFieldMissing` / `KeyArityMismatch` messages now reference the NamedTuple
  class name (e.g. `"Missing key field 'env' on WidgetKey"`).
- A2K005 lint rule simplified: no longer validates `KEY_FIELDS` shape (the
  attribute is gone). Now flags any leftover `KEY_FIELDS = ...` as a v0.5
  migration error and continues to cross-check `connection_param` arity against
  `cls.Key._fields`.

**Removed**

- `KEY_FIELDS: ClassVar[tuple[str, ...]]` — gone. The `__init_subclass__`
  validator that warned on uppercase entries is also gone (NamedTuples enforce
  identifier-shape at the language level).

## 0.4.1 — 2026-05-07

Patch on top of v0.4.0. Three changes: `ty` becomes a hard gate, internal
client-name references are scrubbed from the working tree (and from prior
commits via history rewrite), and two example files are renamed to describe
their shape rather than their inspiring upstream MCP.

**Strict typing**

- `ty` is now a mandatory typecheck step. `make typecheck` no longer skips
  when ty isn't installed — `ty>=0.0.34` is a dev dependency. CI runs
  `uv run ty check src/` between ruff and pytest as a hard gate.
- Pre-commit hook for `ty` runs at `pre-push` (not `pre-commit`) since
  type-checking is comparatively slow.
- Migration: `uv sync --all-extras` if you were previously skipping ty.

**Privacy / generality**

- Connection-name examples no longer reference internal client names.
- Two example files renamed:
  - `examples/a2atlassian_style.py` → `examples/flat_key_style.py`
  - `examples/a2db_style.py` → `examples/multi_field_key_style.py`
- Prose references to `a2atlassian` / `a2db` in source comments, docstrings,
  README, ANTIPATTERNS, and CHANGELOG replaced with descriptive phrases
  ("a Jira/Confluence-wrapping MCP", "a SQL-wrapping MCP"). Real package
  imports (`atlassian-python-api`, `mcp.server.fastmcp`) are unchanged.

**History rewrite**

- v0.4.1 also rewrites the prior 4 commits via `git filter-repo` to scrub
  internal client connection-name references from commit history. Anyone with
  a clone before this point should
  `git fetch --all && git reset --hard origin/main` to sync. (Realistically:
  nobody has a clone — the repo was just published.)

## 0.4.0 — 2026-05-07

Pre-1.0 clean cut. Removes all v0.3 deprecation aliases (no external consumers
to break). Adds CEL projection, completes A2K005, activates A2K010, ships
A2K011, auto-loads pyproject defaults, splits `_select.py`. Internal repo only —
not published to PyPI.

**Breaking changes (deprecation aliases removed):**

- `a2kit.Feature` / `a2kit.FeatureRegistry` — gone. `from a2kit import Feature`
  raises `ImportError` with a migration hint. Use `Router` / `RouterRegistry`
  (kwarg-init).
- `RouterRegistry.feature(...)` decorator — gone. Use `RouterRegistry.router(...)`.
- `MCPRunner` flags `--enable`, `--no-enable`, `--writes` — gone. The synthetic
  `(read or write)` clause translation is removed. Migration:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
- `build_cli(connection_class=...)` kwarg — gone. Derived from
  `store.connection_class`.
- `MCPRunner(connection_class=...)` kwarg — gone. Same derivation.
- `register_ephemeral_connections(args, connection_class)` positional — gone.
  Only `register_ephemeral_connections(args, store=store)` remains.

**New**

- `a2kit.projection` module: `filter_records(records, *, expr)` (CEL boolean
  expression filter), `project_fields(records, *, fields)` (key selection).
  `[projection]` extra brings in `cel-python>=0.5`. Lazy-imported; missing
  dep raises `ProjectionUnavailable`.
- `a2kit.format_response(data, *, filter="", fields=None, ...)` composes
  filter → projection → truncation → format routing.
- `@a2kit.tool(cel_filter_param="filter", fields_param="fields")` auto-threads
  the named function args into `format_response`.
- New exceptions: `ProjectionUnavailable`, `InvalidFilterExpression`.
- `MCPRunner` auto-loads `[tool.a2kit.runner] default_select` from the nearest
  `pyproject.toml` (walks up from CWD). Resolution order: explicit kwarg →
  pyproject value → hard default `"default and not write and not destructive"`.
- `[tool.a2kit.capabilities]` table in `pyproject.toml`. Each entry is
  registered into `a2kit.capabilities` at `MCPRunner.__init__` time. Same
  `CapabilityRecord` validation as the code-side path.
- **A2K010** lint activated: scans `default_select=...`, `parse_select(...)`,
  `--select "<expr>"` literals in source, `scripts/*.sh`, `Makefile`, and
  `pyproject.toml`. Unknown atoms emit `A2K010` with `difflib` suggestions.
- **A2K011** advisory lint: `@a2kit.tool` returning raw `dict`/`Mapping` is
  flagged ("prefer Pydantic BaseModel for richer schema snapshots").
  Configurable via `[tool.a2kit.lint] disabled = ["A2K011"]`. Suppressible
  via `# noqa: A2K011` on the function definition line.
- **A2K005 completed**: cross-checks tool `connection_param` type annotation
  against the resolved store's `KEY_FIELDS` arity. `str` for arity > 1 is
  rejected; `tuple[...]`, typed key model, or `dict[str, str]` accepted.
  Falls back to advisory when the store can't be resolved within the file.

**Cleanups / refactors**

- `_select.py` split into `_select_parse.py` (~110 LOC) + `_select_eval.py`
  (~40 LOC) + `_select.py` façade. Public re-exports unchanged.
- `examples/projection.py`, `examples/cel_filter_tool.py`,
  `examples/toml_capabilities.py`, `examples/v04_minimal_mcp.py` — new.
- ANTIPATTERNS.md adds entries 14–18 (Pydantic class-attr fields, runtime
  `Capability` alias, forward refs + `__future__` annotations, opt-in pytest
  plugins, hard breaks vs synthetic deprecation clauses).
- `tests/test_v04.py` covers projection, A2K005 multi-field, A2K010, A2K011,
  TOML capability loading, removal guards.

**No PyPI publish.** Repo push is the only release channel for v0.4.

## 0.3.1 — 2026-05-07

Patch on top of v0.3.0. Adds Router (Pydantic) + capabilities + select grammar
+ Pydantic configs + strict types. Backward-compatible aliases for one cycle.

**New**

- `Router` (Pydantic `BaseModel`, generic over `ConnT`) replaces `Feature`.
  Subclass and instantiate via kwargs: `IssuesRouter(name="issues", capabilities={Cap.EXTERNAL})`.
- `RouterRegistry.apply()` sets a thread-local `_active_router`; the fat
  `@a2kit.tool` decorator reads this via the **auto-tag seam** and merges
  the router's name + capabilities + `Cap.READ`/`Cap.WRITE` (per phase) onto
  every registered tool's tag set.
- `Cap` constants (`Cap.READ`, `Cap.WRITE`, `Cap.DESTRUCTIVE`, `Cap.EXPENSIVE`,
  `Cap.PII`, `Cap.EXTERNAL`).
- `a2kit.capabilities` namespace — register custom caps:
  `a2kit.capabilities.register("tickets-management", description="...")`.
- `--select` boolean expression flag on `MCPRunner`. Grammar:
  atoms (router/tool/capability names), operators `and`/`or`/`not`,
  optional `tool:` / `router:` / `cap:` namespace prefix, parentheses.
  Default: `default and not write and not destructive`.
- `a2kit.sel(...)` typed builder mirrors the CLI grammar via `&`, `|`, `~`.
- `SelectExpr` (Pydantic AST), `SelectAtom`, `parse_select()`.
- Pydantic configs: `ToolConfig`, `RunnerConfig`, `BudgetConfig` (all
  `extra="forbid"`, `frozen=True`).
- `ConnectionInfo.__init_subclass__` validates `KEY_FIELDS` shape (tuple,
  non-empty, identifier per entry, lowercase warned).
- `ConnectionStore.load(...)` unwraps `pydantic.ValidationError` and re-raises
  the underlying `KeyArityMismatch` / `KeyFieldMissing` / `InvalidConnectionKey`.
- `UnknownCapability` exception with `difflib`-based `suggestions=[...]`.
- New lint rules:
  - **A2K008** — Name collision across router/tool/capability namespaces.
  - **A2K009** — Raw built-in capability string (`'write'` instead of `Cap.WRITE`).
  - **A2K010** — Reserved (v0.4) — unknown atom in `--select` expressions.
- Ruff `ANN` rules added to `[tool.ruff.lint]` selection. `tests/` and
  `examples/` paths get per-file ignores for `ANN001`/`ANN201`/etc.
- New examples: `examples/router_class.py`, `examples/select_grammar.py`,
  `examples/typed_decorator.py`. Updated `examples/v03_minimal_mcp.py`,
  `examples/feature_class.py`.
- `make typecheck-strict` target (graceful fallback if ty unavailable).
- `.pre-commit-config.yaml`, `package.json` (jscpd + actionlint),
  `.jscpd.json`, `scripts/find_similar.py` (similar-tool-name detector).

**Breaking changes**

- `--enable` / `--no-enable` / `--writes` flags on `MCPRunner` are deprecated.
  They still work for one cycle (with `DeprecationWarning`) and are translated
  internally to a `--select` expression.

  Migration recipe:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
  - `--enable issues --writes` → `--select "router:issues and (read or write)"`

**Deprecations (one-cycle warning, removal in v0.4)**

- `Feature` / `FeatureRegistry` (use `Router` / `RouterRegistry`).
  Class-attribute style (`class IssuesFeature(Feature): name = "issues"`) is
  not supported under Pydantic; use `IssuesRouter(name="issues", ...)` instead.
- `RouterRegistry.feature(...)` decorator (use `RouterRegistry.router(...)`).
- `--enable` / `--no-enable` / `--writes` (use `--select`).

**Internal renames (underscore-prefixed; no external impact)**

- `a2kit/_capabilities.py`, `a2kit/_select.py`, `a2kit/_router_state.py`,
  `a2kit/_configs.py` — all leading-underscore internals.

## 0.3.0 — 2026-05-07

Feature class, KEY_FIELDS, server-auto-register, lint subpackage. Internal-only
release one day after v0.2 — applies a clean cut where it makes sense.

**Breaking changes**

- `KEY_PARTS: ClassVar[int | None]` → `KEY_FIELDS: ClassVar[tuple[str, ...]]`.
  No alias — pre-1.0 clean cut. Migration: replace `KEY_PARTS = N` with the
  field-named tuple, e.g. `KEY_FIELDS = ("project", "env", "db")`. Default
  `("name",)` covers the single-key case, so subclasses with `KEY_PARTS = 1`
  can simply drop the line.
- `build_cli(connection_class=...)` and `MCPRunner(connection_class=...)` are
  deprecated. The store knows its model — use `build_cli(store, name="...")`
  and `MCPRunner(server, store=store)`. Passing `connection_class=` still
  works for one cycle, with a `DeprecationWarning`.
- `register_ephemeral_connections(args, connection_class)` → prefer
  `register_ephemeral_connections(args, store=store)`. Old shape works with a
  warning.

**New**

- `@a2kit.tool(server=server, ...)` auto-registers the wrapped function with
  FastMCP's tool manager. Idempotent when stacked under an explicit
  `@server.tool()` (innermost) — the decorator detects an existing entry by
  name and skips. The single-decorator path is the new default; stacked form
  remains for callers who need explicit FastMCP options.
- `ConnectionInfo.KEY_FIELDS` — named-tuple key shape. Default `("name",)`.
  `ConnectionStore.load(...)` now accepts kwargs (`load(project=..., env=..., db=...)`),
  tuples, lists, positional args, and bare-string sugar for the single-field
  default.
- New typed exceptions: `KeyFieldMissing`, `KeyArityMismatch`.
- `ConnectionStore.connection_class` — exposes the bound model class.
- `a2kit.scaffold.Feature` — base class bundling enricher + snapshot_dir +
  cassette_dir + register hooks. The v0.2 `@registry.feature(name, ...)`
  decorator path is unchanged. Register an instance via `registry.add(MyFeature())`.
- `a2kit.docs.register_param_doc(name, text)` + `a2kit.docs.param_doc(name)`.
  Registered text is auto-injected into a tool's docstring when the existing
  docstring doesn't mention the parameter. Explicit text wins.
- `a2kit.lint` subpackage:
  - **Static rules:** `A2K001` (tool decorator missing param), `A2K002`
    (`-> str` returns), `A2K003` (module-local Pydantic return), `A2K004`
    (canonical connection-param helper), `A2K005` (`KEY_FIELDS` shape +
    usage), `A2K006` (duplicate param description).
  - **Runtime checks:** `A2KR001` (snapshot presence), `A2KR002` (per-tool
    budget), `A2KR003` (total schema budget), `A2KR004` (similar tool names).
  - CLI: `uvx a2kit lint paths...` and `uvx a2kit check --import path:server`.
  - Configurable via `[tool.a2kit.lint]` / `[tool.a2kit.check]`. Per-line
    `# noqa: A2KXXX`.
  - See `LINT.md` for rationale and examples.

**Examples added**

- `examples/v03_minimal_mcp.py` — < 30 LOC for a 2-tool MCP using `@a2kit.tool(server=...)`.
- `examples/feature_class.py` — `Feature` base class with enricher + snapshot dir.
- `examples/key_fields.py` — all four `load()` call shapes against a 3-part key.

Existing examples (`runner.py`, `scaffold_cli.py`, `feature_modules.py`) updated
to drop the now-redundant `connection_class=` kwarg.

**Deprecations (one-cycle warning, removal in v0.4)**

- `build_cli(connection_class=...)`
- `MCPRunner(connection_class=...)`
- `register_ephemeral_connections(args, connection_class)` (positional)

## 0.2.0 — 2026-05-07

Production-grade primitive set. Promotes a2kit from "ready for first external
consumer" to a foundation that absorbs every recurring MCP boilerplate at n=2.
All v0.1 API still imports unchanged; the bare `@a2kit.tool()` is byte-equivalent
to `@a2kit.tools.tool()` from v0.1.

**New modules:**

- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`. Vendored
  TOON encoder (~12 LOC) + recursive truncation + canonical envelope.
- `a2kit.docs` — `connection_param_doc(name, *, cli, example, custom_suffix)`.
  One canonical paraphrase for the connection-param docstring (eliminates
  per-tool phrasing drift).
- `a2kit._cassette` (re-exported as `a2kit.testing.cassette`) — vcrpy thin
  wrapper. Decorator + sync/async context manager.

**New scaffold primitives:**

- `a2kit.scaffold.MCPRunner` — wraps `server.run()` with `--register`,
  `--scope`, `--enable`, `--no-enable`, `--writes`, `--http [host:port]` parsing.
  Sets the thread-local transport seam used by `streaming=True` tools.
  Skippable: calling `server.run()` directly is fully supported.
- `a2kit.scaffold.FeatureRegistry` — decorator-style feature-module
  registration with `default=` flag and `apply(server, store, *, enabled,
  include_writes)`.

**Fat `@a2kit.tool` decorator** (extends v0.1 — every new arg is optional):

- `store=` + `connection_param=` + `info_kwarg=` — connection lookup +
  injection.
- `ephemeral=` — in-memory connections take priority over store.
- `resolver_registry=` — recursive `${ENV}` / `op://` resolution on every
  string field of the loaded `ConnectionInfo`.
- `write=True` — enforces `read_only` check; raises `WriteNotAllowed`.
- `xml_guard=True` (default) — refuses any `str` arg containing
  `<parameter name=`; raises `ToolXMLContamination`.
- `otel=True` (default) — wraps the call in `a2kit.tool.<name>` span when a
  non-default tracer provider is configured; no-op otherwise. Lazy import,
  optional `[otel]` extra.
- `streaming=True` — async-iterator returns collected on stdio, passed
  through on HTTP.
- `tool_name=` — explicit name for the OTel span (defaults to `__name__`).
- Public top-level alias `a2kit.tool` (v0.1 `a2kit.tools.tool` retained).
- Standalone helper `a2kit.tools.assert_clean_string(value, param_name)`.

**Pytest plugin additions:**

- `--update-cassettes` flag.
- `update_cassettes` boolean fixture.

**New exceptions:** `WriteNotAllowed`, `ToolXMLContamination`.

**Optional extras:**

- `[otel]` — `opentelemetry-api>=1.20`. Lazy-imported.
- `[testing]` — `vcrpy>=6`. Lazy-imported via `a2kit.testing.cassette`.

**Examples added:** `fat_tool.py`, `runner.py`, `formatter.py`,
`feature_modules.py`, `streaming_tool.py`, `cassette_test.py`. `scaffold_cli.py`
updated to use `MCPRunner`. `make examples` runs all of them end-to-end.

**Anti-patterns consolidated:** `ANTIPATTERNS.md` at repo root — 13 entries,
each with citation.

**No deprecations.** `a2kit.tools.tool` still exported.

## 0.1.0 — 2026-05-07

Initial thin-library release. Promotes a2kit from single-primitive spike to a v0.1
library ready for first external consumer.

**Public API surface:**

- `ConnectionInfo`, `ConnectionStore`, `default_config_dir` — TOML-backed
  named-connection store. Already in 0.0.1.
- `resolve_token`, `ResolverRegistry`, `resolve_env`, `resolve_op`, `resolve_literal`,
  `default_registry` — token resolvers (`${ENV_VAR}`, `op://...`, literal). Already
  in 0.0.1.
- `tools.tool` decorator — composes with FastMCP's `@server.tool()`. Refuses
  `-> str` returns at decoration time (`InvalidToolReturnTypeError`); rewrites
  return annotations on both wrapper and wrapped function. Optional `enricher`
  routes exceptions through an `ErrorEnricher`.
- `tools.preserve_return_annotation` — public utility for the annotation-rewrite
  trick alone, without the rest of `tool(...)`.
- `errors.ErrorEnricher` Protocol — `enrich(exc, *, tool_name) -> Exception`.
- `errors.EnricherRegistry` — chains enrichers in registration order; first
  divergent return wins.
- `errors.ConnectionNotFoundEnricher` — built-in enricher; adds
  `available_connections` and a `difflib` suggestion to `ConnectionNotFound`
  exceptions.
- `scaffold.build_cli(store, connection_class, name)` — Click group with
  `login`/`logout`/`connections list`/`connections show`/`connections delete`.
  Author adds their own commands via `cli.add_command(...)`.
- `scaffold.register_ephemeral_connections(args, connection_class)` — parses
  `--register KEY field=val ...` blocks from argv into in-memory connections.
- `scaffold.scope_filter(store, scope)` — read-only filtered store view.
- `testing.snapshot_schemas(server, dir)` — writes one compact-JSON file per
  FastMCP tool (file size = byte-accurate token-budget proxy).
- `testing.assert_schemas_match(server, dir)` — raises `SchemaSnapshotMismatch`
  on drift; message contains a unified diff.
- `pytest_plugin` — opt-in via `pytest_plugins = ["a2kit.pytest_plugin"]` in
  the consumer's `conftest.py`. Provides `schema_snapshot` fixture and
  `--update-schema-snapshots` flag.
- New exceptions: `InvalidToolReturnTypeError`, `SchemaSnapshotMismatch`.

**No deprecations.** All 0.0.1 API still imports unchanged.

**Out of scope (deferred):**

- Retry/rate-limit base client (anticipated at n=1; confirm or kill at n=3).
- Feature-module registration with `--enable` (anticipated at n=1).
- Pagination unification (anticipated at n=1).
- Output-format router (TSV/TOON/JSON) — module-level concern, not a primitive.
- Token-budget defaults — module-level concern.
- OTel integration — deferred to v0.2.

## 0.0.1 — 2026-05-07

Initial spike. `ConnectionStore` extracted from two upstream MCPs (a SQL
wrapper and a Jira/Confluence wrapper); pluggable `ResolverRegistry`; typed
exceptions on resolver failure.
