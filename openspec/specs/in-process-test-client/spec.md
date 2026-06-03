# in-process-test-client Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async context manager that runs the **real FastMCP in-memory transport** in-process and exposes capture surfaces for assertions. The test client SHALL build a `FastMCP` server via `build_mcp_server(app)` and connect to it through `fastmcp.Client(transport=server, ...)`, exercising the same dispatch path production MCP transport uses.

The test client SHALL NOT subclass `StderrToolContext` or otherwise construct a CLI-shaped fake of the runtime Context.

App lifecycle around the test session SHALL follow the `app-lifecycle` capability: the App's `__aenter__` runs before the first invoke and its `__aexit__` runs after the block exits. Startup and shutdown bookends are expressed as DI-managed resources registered with `app.provide(T, factory)`; their `__aenter__` / `__aexit__` are entered and unwound by the framework around the App lifecycle. Lifecycle is the async-context-manager protocol plus lazy first-use resource entry.

#### Scenario: ctx received by tools is a real fastmcp.Context

- **WHEN** a tool's body runs under `async with a2kit.testing.client(app)`
- **THEN** the ctx argument satisfies `isinstance(ctx, fastmcp.Context)`
- **AND** `isinstance(ctx, StderrToolContext)` is False

#### Scenario: invoke runs the same code path as production dispatch

- **WHEN** a test calls `await client.invoke("tasks.create", name="x")` on an app with `TasksRouter`
- **THEN** the dispatcher resolves DI, runs decorator processing, executes the tool body, and returns the value the tool returned, with the dispatch routed through the real FastMCP server

#### Scenario: App lifecycle fires around the test session

- **WHEN** a test enters `async with a2kit.testing.client(app) as c:` and exits the block
- **THEN** the App's `__aenter__` ran before the first invoke and its `__aexit__` ran after the block exited, each exactly once
- **AND** DI-managed resources registered via `app.provide(T, factory)` had their `__aenter__` / `__aexit__` entered and unwound around the session

### Requirement: Event and progress capture

The test client SHALL capture every event, progress update, log call, and report emitted via `ctx` during a tool invocation, exposing them as ordered lists. Log capture SHALL surface as structured `LogLine` entries (level, message, fields, elapsed_ms); a derived `logs_text` property renders each via `format_ldd_line` for tests that need the wire-format string.

#### Scenario: events captured with payload and elapsed_ms

- **WHEN** a tool calls `await event(ctx, "import.started", n=10)` and later `await event(ctx, "import.complete", count=10)`
- **THEN** `client.events` contains both entries in order, each with `name`, `payload`, and `elapsed_ms` fields

#### Scenario: progress captured as (current, total) tuples

- **WHEN** a tool calls `await ctx.report_progress(5, total=10)`
- **THEN** `client.progress[-1] == (5, 10)`

#### Scenario: log capture as dicts

- **WHEN** a tool calls `await a2kit.log.info("starting", batch=1)`
- **THEN** `client.logs[-1]` is a dict with `level` (uppercase shorthand like `"INFO"`), `msg`, `fields` (`{"batch": 1}`), and `elapsed_ms` keys

#### Scenario: typed reports captured as dicts

- **WHEN** a tool calls `await a2kit.log.info(BatchReport(batch=1, accepted=5))`
- **THEN** `client.reports[-1]` is a dict with `type` (the class name), `body` (`model_dump()` payload), and `elapsed_ms` keys

#### Scenario: wire payload prefixes a2kit-internal keys to dodge LogRecord collisions

- **GIVEN** an `a2kit.log.info("evt", payload={"k": 1})` call on the MCP transport
- **WHEN** the server-side ctx.log call passes through FastMCP's `_log_to_server_and_client` (which calls `to_client_logger.log(..., extra=...)`)
- **THEN** the `extra` dict contains `a2kit_kind`, `a2kit_name`, `a2kit_payload`, `a2kit_elapsed_ms` — none of which collide with Python `LogRecord` reserved attributes
- **AND** the client-side `log_handler` un-prefixes these back to the public capture shape (`{"name", "payload", "elapsed_ms"}`)

### Requirement: Wire-format rendering

The test client SHALL expose `render_as(format, value)` that runs the value through `a2kit.packages.formatter` and returns the rendered output for assertions.

#### Scenario: render a tool return value as JSON

- **WHEN** a test calls `client.render_as("json", result)` on a Pydantic model return
- **THEN** the call returns the same dict the MCP transport would emit

#### Scenario: render a tool return value as TSV

- **WHEN** a test calls `client.render_as("tsv", result)` on a `list[ScalarOnlyModel]` return
- **THEN** the call returns the TSV string the CLI would emit

### Requirement: Tool-descriptor introspection

The test client SHALL expose `client.tools()` returning the list of tool descriptors (name, input schema, output schema, annotations) the dispatcher would advertise.

#### Scenario: tools list matches MCP server registration

- **WHEN** a test calls `client.tools()` after composing the App
- **THEN** the returned descriptor list has the same names and schemas as `build_mcp_server(app).tools()` would advertise

### Requirement: Connection passthrough

The test client SHALL accept a `connection=...` kwarg on `invoke(...)` and route it through the same DI chain as CLI / MCP transports.

#### Scenario: tool with a connection-scoped dependency resolves correctly

- **WHEN** a test calls `await client.invoke("tasks.list_tasks", connection="default")` on the tracker example
- **THEN** the tool receives the same `TrackerStore` instance the CLI would receive for `connection=default`

### Requirement: Null context shim for unit-testing internal functions

The library SHALL expose `a2kit.testing.null_context() -> ToolContext` returning a no-op object that satisfies the `fastmcp.Context` interface. Every public method of `fastmcp.Context` SHALL be present on the shim. Async methods SHALL return immediately without I/O. Properties (`request_id`, `client_id`, etc.) SHALL return fixed sentinel values documented in the docstring.

The shim is for **unit tests of internal phase functions that bypass `a2kit.testing.client`**. Production code SHOULD take `ctx: ToolContext` (non-Optional) and tests SHOULD construct one of these shims rather than passing `None`.

#### Scenario: Null context can be passed to a function expecting ToolContext

- **GIVEN** an async function `async def fetch_tier(ctx: a2kit.ToolContext, url: str) -> str` that calls `await ldd.event(ctx, "tier.started", url=url)` internally
- **WHEN** a unit test calls `await fetch_tier(a2kit.testing.null_context(), "https://...")`
- **THEN** the call succeeds, the event call is a silent no-op, and no `AttributeError` is raised

#### Scenario: All logging methods are no-ops

- **WHEN** test code calls `await ctx.info("hi")`, `await ctx.warning("hi")`, `await ctx.error("hi")`, `await ctx.debug("hi")` on a null context
- **THEN** all calls return None and produce no observable side effect

#### Scenario: report_progress is a no-op

- **WHEN** test code calls `await ctx.report_progress(0.5, 1.0)` on a null context
- **THEN** the call returns None and produces no observable side effect

#### Scenario: request_id returns a fixed sentinel

- **WHEN** test code reads `ctx.request_id` on a null context
- **THEN** the value is the literal string `"null-context"`

### Requirement: null_context is in a2kit.testing alongside client

The `a2kit.testing` module SHALL re-export `null_context` (alongside `client` and `TestClient`). The shim implementation SHALL live in `src/a2kit/packages/testing/null_context.py`.

#### Scenario: Re-export

- **WHEN** test code runs `from a2kit.testing import null_context`
- **THEN** the import succeeds

### Requirement: Wire-encoded payload capture via call_wire

The `TestClient` SHALL expose an async method
`call_wire(tool_name, *, connection=None, **kwargs)` that dispatches
the tool identically to `invoke` and then returns the
formatter-encoded structured-content payload — byte-identical to
what an out-of-process MCP client would receive on the
`structuredContent` channel.

`call_wire` SHALL resolve the wire format by reading the tool
descriptor's cached `format_hint` (populated at registration time
per the `type-driven-format-routing` capability). `call_wire` SHALL
NOT re-run any type-inference heuristic and SHALL NOT accept an
explicit format-hint argument. The encoding pass SHALL go through
`a2kit.packages.formatter.format_response(value, format_hint=hint)`
and the returned payload SHALL be the `Response.data` field of the
formatter's result.

The dispatch path inside `call_wire` SHALL be the same one `invoke`
uses: DI resolution, decorator processing, tool body execution, and
all capture surfaces (`events`, `progress`, `logs`, `reports`) SHALL
populate exactly as they do for `invoke`.

`invoke` itself SHALL remain unchanged — it continues to return the
raw Python value the tool body produced, without a formatter pass.

#### Scenario: JSON-shaped return rendered as a dict

- **GIVEN** a tool annotated `-> Task` (single `BaseModel`) whose
  descriptor's `format_hint` resolves to `"json"`
- **WHEN** a test calls `await client.call_wire("tools.get_task",
  id="x")`
- **THEN** the returned value equals `task.model_dump(mode="json")`
  for the `task` the tool returned

#### Scenario: TSV-shaped return rendered as a TSV string

- **GIVEN** a tool annotated `-> list[Task]` where `Task` is
  scalar-only, whose descriptor's `format_hint` resolves to `"tsv"`
- **WHEN** a test calls `await client.call_wire("tools.list_tasks")`
- **THEN** the returned value is the TSV string produced by
  `encode_tsv` — header line in declared `Task.model_fields` order,
  one row per item, `\n` line terminator

#### Scenario: page-tsv return rendered as the JSON envelope

- **GIVEN** a tool annotated `-> Page[Task]` where `Task` is
  scalar-only, whose descriptor's `format_hint` resolves to
  `"page-tsv"`
- **WHEN** a test calls `await client.call_wire("tools.search")`
- **THEN** the returned value is the JSON-encoded string of the
  hybrid envelope `{"items": "<tsv>", "next_cursor": ...,
  "_items_format": "tsv", ...}` exactly as `encode_page_tsv`
  produces it

#### Scenario: auto-detected format matches production routing

- **GIVEN** two tools — one annotated `-> list[ScalarTask]` and one
  annotated `-> list[NestedTask]` (NestedTask has a list field) —
  registered on the same App
- **WHEN** a test calls `call_wire` on each
- **THEN** the first returns a TSV string and the second returns a
  JSON-shaped value (dict / list-of-dicts), reflecting the
  descriptor's cached `format_hint` for each tool

#### Scenario: capture surfaces populate on call_wire

- **GIVEN** a tool that calls `await event(ctx, "started")`, `await
  ctx.report_progress(1, total=2)`, and `await ldd.info(ctx,
  "halfway")` before returning
- **WHEN** a test calls `await client.call_wire(tool_name)`
- **THEN** `client.events`, `client.progress`, and `client.logs`
  contain the emitted entries in order — same shape as if the test
  had called `client.invoke`

#### Scenario: invoke returns the raw Python value unchanged

- **GIVEN** a tool annotated `-> list[ScalarTask]` whose descriptor
  routes to `"tsv"`
- **WHEN** a test calls `await client.invoke(tool_name)`
- **THEN** the returned value is the `list[ScalarTask]` the tool
  body returned — not a TSV string — confirming that adding
  `call_wire` did not change `invoke` semantics

### Requirement: Return value contract — FastMCP-marshaled

`TestClient.invoke(...)` SHALL return the FastMCP-unmarshaled structured payload (`result.data` from `fastmcp.Client.call_tool`). For tools returning user-declared types (`pydantic.BaseModel`, `dataclass`), FastMCP synthesizes a field-equivalent Pydantic-validated type with the same field values but a distinct class identity. Tests asserting on user-declared class identity migrate to field-wise comparison or `model_dump()` equality.

#### Scenario: BaseModel return arrives as field-equivalent synthetic type

- **GIVEN** a tool `async def m() -> M` returning `M(x=42)` where `M` is a `pydantic.BaseModel`
- **WHEN** the test calls `await client.invoke("m")`
- **THEN** the returned value has `.x == 42` and `model_dump() == {"x": 42}`
- **AND** the returned value's class identity is not guaranteed to be the user-declared `M`

### Requirement: Exception envelope contract

Tool-body exceptions SHALL surface from `TestClient.invoke(...)` as `fastmcp.exceptions.ToolError` carrying the a2kit-owned structured envelope from `mcp-structured-wire-error-envelope` — `json.loads(str(exc))` yields `{"class": <ExceptionClassName>, "message": <str(exc)>, [traceback when App(debug=True)]}`. Tests asserting on Python exception class identity parse the envelope.

#### Scenario: ValueError envelope round-trip

- **GIVEN** a tool body `raise ValueError("boom")`
- **WHEN** the test calls `await client.invoke(name)` and catches the exception
- **THEN** the caught exception is `fastmcp.exceptions.ToolError`
- **AND** `json.loads(str(exc)) == {"class": "ValueError", "message": "boom"}`

### Requirement: Hidden `_meta.*` tools invocable in tests

The test client SHALL re-enable the `_meta` tag on the server it builds so hidden protocol-meta tools (e.g. `_meta.health`) are invocable via `invoke()`. Production MCP transport hides them via `server.disable(tags={"_meta"})`; the test client opts back in so test authors can probe health and other meta surfaces. The `_meta.health` tool exists only on Apps that have at least one `@app.health_check` registration — the framework does not accept an `App(health_tool=True)` constructor keyword (it does not exist).

#### Scenario: _meta.health invocable through test client

- **GIVEN** an `App("a")` with at least one `@app.health_check`-registered function
- **WHEN** the test calls `await client.invoke("_meta.health")`
- **THEN** the call succeeds and the result includes the aggregated health payload

### Requirement: TestClient SHALL surface renamed method names with embedded migration hints

The `TestClient` class SHALL intercept attribute access on names that correspond to methods renamed in a prior release and raise `TypeError` (not `AttributeError`) with an error message that includes the new method name and an explicit "no alias is provided" note. Genuinely-unknown attribute names SHALL continue to raise the
standard `AttributeError`.

The framework SHALL NOT host backward-compat aliases for renamed
surfaces. Aliases hide migrations from consumers' read paths.
Renames are effective immediately; the only contract is that the
error message names the new attribute.

#### Scenario: Renamed `.call` raises TypeError with hint

- **GIVEN** a v0.32-style call shape `await client.call("demo.ping", msg="hi")`
- **WHEN** the call is awaited against v0.33+
- **THEN** `TypeError` is raised
- **AND** the message contains `"renamed"` and `"invoke"`

#### Scenario: Genuinely unknown attribute falls through to AttributeError

- **GIVEN** an access `client.completely_unknown_method`
- **WHEN** the attribute resolves
- **THEN** `AttributeError` is raised (not `TypeError`)
- **AND** the message names the missing attribute

#### Scenario: Canonical name still works

- **GIVEN** `await client.invoke("demo.ping", msg="hi")`
- **WHEN** the call is awaited
- **THEN** the tool dispatches and returns its payload (no `TypeError`)

### Requirement: Async DI resolution test seam

The system SHALL provide `a2kit.testing.resolve(app, type_)` — an
async helper that resolves a registered type through the App's
container using the same path as production tool dispatch. The
function SHALL run the full DI resolution chain, building the type
via its registered factory (chaining constructor-parameter
resolution), entering `__aenter__` for resources, and recording
cleanup on the appropriate scope's stack (root for SINGLETON,
child for SCOPED).

`resolve` SHALL be the async sibling of `peek`. Where `peek` reads
already-cached singletons from `Container._singletons`, `resolve`
triggers the full resolution chain — including building the type
on first call. Subsequent calls SHALL return cached instances per
the registered scope's semantics.

Callers SHALL invoke `resolve` inside an entered app context
(`async with a2kit.testing.client(app):` or `async with app:`) so
the cleanup stack is alive to receive recorded `__aexit__`
callbacks. Calling outside an entered app is undefined and matches
today's `await app.container().get(T)` semantics — resources may
end up half-entered without a scope to exit them.

`a2kit.testing.resolve` SHALL be importable as
`from a2kit.testing import resolve` and appear in
`a2kit.testing.__all__`.

#### Scenario: resolve runs the DI chain on first call

- **GIVEN** `app.provide(_Inner)` where `_Inner.__init__` increments a class-level counter
- **WHEN** the test does `async with app: instance = await a2kit.testing.resolve(app, _Inner)`
- **THEN** `_Inner.instances_created == 1`
- **AND** `instance` is an `_Inner`

#### Scenario: resolve enters resources via __aenter__

- **GIVEN** `_Inner` implements `__aenter__` / `__aexit__` with counters and is registered as a singleton
- **WHEN** the test resolves `_Inner` once inside `async with app:`
- **THEN** `_Inner.entered == 1` after the resolve returns
- **AND** `_Inner.exited == 0` while the lifespan is still in flight
- **AND** `_Inner.exited == 1` after the lifespan exits

#### Scenario: resolve returns cached singleton on second call

- **GIVEN** `_Inner` registered as a singleton (default `per_call=False`)
- **WHEN** the test calls `resolve(app, _Inner)` twice in the same lifespan
- **THEN** both calls return the same instance by identity
- **AND** `_Inner.__aenter__` was invoked exactly once

#### Scenario: resolve walks the dependency chain

- **GIVEN** `app.provide(_Inner)` and `app.provide(_Outer)` where `_Outer`'s factory takes an `_Inner` parameter
- **WHEN** the test calls `await a2kit.testing.resolve(app, _Outer)` inside `async with app:`
- **THEN** the returned `_Outer` is fully constructed with the resolved `_Inner` injected into its factory
- **AND** subsequent `resolve(app, _Inner)` returns the same `_Inner` instance the outer factory received

### Requirement: Lazy-thunk testing constructor

The system SHALL provide `a2kit.testing.lazy(value)` — a synchronous
factory that returns a zero-argument async callable conforming to the
`Lazy[T] = Callable[[], Awaitable[T]]` shape used at the tool seam.

The returned thunk SHALL return the original `value` unchanged on
each invocation. The framework SHALL NOT deep-copy, cache, or
otherwise transform the value; callers needing per-call freshness
SHALL construct their own thunk.

`a2kit.testing.lazy` SHALL be importable as
`from a2kit.testing import lazy` and SHALL appear in
`a2kit.testing.__all__`. `Lazy` SHALL remain a `TypeAlias` — no
runtime `Lazy.of` class-method is added.

#### Scenario: lazy(value) returns a zero-arg async callable

- **GIVEN** an arbitrary value `v = object()`
- **WHEN** a test calls `thunk = a2kit.testing.lazy(v)`
- **THEN** `thunk` is callable with zero arguments
- **AND** `await thunk()` returns `v`
- **AND** `await thunk() is v` (identity preserved, no copy)

#### Scenario: lazy thunk satisfies the Lazy[T] tool kwarg

- **GIVEN** a tool declaring `browser: Lazy[BrowserPool]`
- **WHEN** a test injects a fake via `lazy(fake_browser)` through
  the DI override surface
- **THEN** the tool body's `await browser()` returns `fake_browser`
  and no `TypeError` is raised by the dispatcher's Lazy unwrapping
  path

### Requirement: Ambient-LDD pytest fixture

The system SHALL provide `a2kit.testing.ambient_for_tests` — a
`pytest.fixture` that wraps test execution in an active LDD ambient
state, allowing tests to call orchestrator or phase functions
directly (bypassing `TestClient.invoke`) without raising
`AmbientContextMissing`.

The fixture SHALL be opt-in (not `autouse=True` at the framework
level). Consumers requiring project-wide ambient state SHALL
re-export it with `autouse=True` in their own `conftest.py`. This
preserves the loud-by-default contract of `AmbientContextMissing`
outside test contexts that explicitly request the ambient.

The fixture SHALL default to:
- `ctx = null_context()`
- `events_enabled = False`
- `reports_enabled = False`

Consumers requiring different flag combinations SHALL construct
their own fixture using `ldd_state_for_call` directly. The
framework SHALL NOT expose parametric variants of
`ambient_for_tests`.

#### Scenario: tests using the fixture can emit LDD events without error

- **GIVEN** a pytest test function declaring `ambient_for_tests`
  in its signature
- **WHEN** the test body calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call completes without raising
  `AmbientContextMissing`

#### Scenario: tests not using the fixture still fail loud

- **GIVEN** a pytest test function that does NOT depend on
  `ambient_for_tests` and is not under an autouse re-export
- **WHEN** the test body calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call raises `AmbientContextMissing` with the v0.33
  hint message

#### Scenario: default flags suppress event/report emission

- **GIVEN** a test using `ambient_for_tests`
- **WHEN** the test body calls `await a2kit.log.info("evt")` and
  `await a2kit.log.info(SomeReport(...))`
- **THEN** neither emission produces a wire-side effect (no sinks
  fire), consistent with `events_enabled=False` and
  `reports_enabled=False`

#### Scenario: fixture is importable from the public surface

- **WHEN** a consumer writes `from a2kit.testing import ambient_for_tests`
- **THEN** the import resolves and the imported object is a
  pytest fixture (carries the `_pytestfixturefunction` marker
  attribute)

### Requirement: Pre-decorated autouse ambient-LDD fixture

The system SHALL provide `a2kit.testing.ambient_for_tests_autouse` —
a peer of `ambient_for_tests` that is pre-decorated with
`pytest.fixture(autouse=True)` at the framework level. Consumers
that want project-wide ambient binding SHALL re-export this single
name in their `conftest.py` without touching pytest internals.

The autouse variant SHALL share the same default flag values as
`ambient_for_tests` (`ctx = null_context()`, `events_enabled = False`,
`reports_enabled = False`) and SHALL produce equivalent runtime
behavior; the only difference is the `autouse=True` decoration.

The existing `ambient_for_tests` fixture SHALL remain unchanged.
Consumers that adopted the documented `__wrapped__` re-export
pattern SHALL continue to work without migration. The framework
SHALL NOT deprecate either flavor.

The `OPERATIONAL_CONTRACTS.md` Q-AmbientForTests entry SHALL
document both flavors with a one-line decision rule:
project-wide-binding consumers import `_autouse`; per-test opt-in
consumers import the bare `ambient_for_tests`.

#### Scenario: autouse variant binds ambient without consumer re-decoration

- **GIVEN** a consumer's `conftest.py` containing only
  `from a2kit.testing import ambient_for_tests_autouse`
- **WHEN** a pytest test in that project calls
  `await a2kit.log.info("evt", k=1)` without declaring any fixture
  in its signature
- **THEN** the call completes without raising `AmbientContextMissing`

#### Scenario: autouse variant exposes pytest fixture metadata

- **WHEN** a test imports
  `from a2kit.testing import ambient_for_tests_autouse`
- **THEN** the imported object carries the
  `_pytestfixturefunction` marker attribute
- **AND** its `autouse` attribute resolves to `True`

#### Scenario: bare ambient_for_tests fixture is unchanged

- **GIVEN** a project that imports only the bare
  `ambient_for_tests` fixture (no autouse re-export)
- **WHEN** a pytest test that does NOT declare `ambient_for_tests`
  in its signature calls `await a2kit.log.info("evt", k=1)`
- **THEN** the call raises `AmbientContextMissing` with the v0.33
  hint message, exactly as before this change

#### Scenario: both flavors share default flag values

- **GIVEN** a test running under `ambient_for_tests_autouse`
- **WHEN** the test body calls `await a2kit.log.info("evt")` and
  `await a2kit.log.info(SomeReport(...))`
- **THEN** neither emission produces a wire-side effect (no sinks
  fire), matching the bare fixture's
  `events_enabled=False` / `reports_enabled=False` defaults

