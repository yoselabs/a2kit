# in-process-test-client Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async context manager that runs the full dispatcher in-process and exposes capture surfaces for assertions.

#### Scenario: invoke runs the same code path as production dispatch

- **WHEN** a test calls `await client.invoke("tasks.create", name="x")` on an app with `TasksRouter`
- **THEN** the dispatcher resolves DI, runs decorator processing, executes the tool body, and returns the value the tool returned

#### Scenario: lifecycle hooks fire around the test session

- **WHEN** a test enters `async with a2kit.testing.client(app) as c:` and exits the block
- **THEN** registered `@app.on_startup` handlers run before the first invoke and `@app.on_shutdown` handlers run after the block exits, exactly once each

### Requirement: Event and progress capture

The test client SHALL capture every event, progress update, log call, and report emitted via `ctx` during a tool invocation, exposing them as ordered lists.

#### Scenario: events captured with payload and elapsed_ms

- **WHEN** a tool calls `await event(ctx, "import.started", n=10)` and later `await event(ctx, "import.complete", count=10)`
- **THEN** `client.events` contains both entries in order, each with `name`, `payload`, and `elapsed_ms` fields

#### Scenario: progress captured as (current, total) tuples

- **WHEN** a tool calls `await ctx.report_progress(5, total=10)`
- **THEN** `client.progress[-1] == (5, 10)`

#### Scenario: typed reports captured as values

- **WHEN** a tool calls `await report(ctx, BatchReport(batch=1, accepted=5))`
- **THEN** `client.reports` contains the `BatchReport` instance unchanged

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

### Requirement: TestClient.override swaps DI-resolved dependencies for the session

The test client SHALL expose `override(type_: type[T], fake: T) -> None` on the `TestClient` instance returned by `a2kit.testing.client(app)`. The method SHALL replace the App container's binding for `type_` with `fake` for the remainder of the `async with` block, restoring the prior binding on `__aexit__` (including exceptional exit).

The signature SHALL be type-parameterised by a `TypeVar` such that mypy / pyright / ty bind `fake` to the same `T` as `type_`. Callers SHALL NOT need `# type: ignore` to swap a fake that satisfies the registered type.

Overrides SHALL cover both DI registration paths:
- types registered via `app.singleton(T, ...)` (cached singletons),
- types registered via `app.provide(T, ...)` (per-call providers).

Overrides SHALL also apply when `type_` was not previously registered (the fake is registered fresh for the duration of the session). Overrides SHALL also clear any async-factory marker on `type_` so synchronous resolve paths return the fake without blocking.

Calling `override` more than once for the same `type_` within one session SHALL apply last-write-wins; only one restore happens at exit (to the pre-session state, not to intermediate values).

The implementation SHALL delegate the three-attribute mutation to `Container._override(type_, fake)` (per the di-container-package capability) — it SHALL NOT reach into `_providers`, `_singletons`, or `_async_factories` directly. The TestClient retains responsibility for capturing the pre-session snapshot (via `Container._snapshot()`) on first call within a session and for restoring it on `__aexit__` (via `Container._restore(snapshot)`).

#### Scenario: Override replaces a singleton-registered dependency

- **GIVEN** an App with `app.singleton(LLMExtractor, lambda: RealLLM())` and a tool that takes `extractor: LLMExtractor`
- **WHEN** test code runs `async with a2kit.testing.client(app) as c:` then `c.override(LLMExtractor, FakeLLM())` then `await c.invoke("foo")`
- **THEN** the tool body receives the `FakeLLM` instance, and `a2kit.testing.peek(app, LLMExtractor)` inside the block also returns the same `FakeLLM`

#### Scenario: Override replaces a per-call provider-registered dependency

- **GIVEN** an App with `app.provide(Store, build_store)` and a tool that takes `store: Store`
- **WHEN** test code calls `c.override(Store, FakeStore())` inside the `async with` block and then `await c.invoke("foo")` multiple times
- **THEN** every invocation receives the same `FakeStore` instance the test passed in (the provider is shadowed by a constant-factory for the duration of the override)

#### Scenario: Override is restored on normal exit

- **GIVEN** `a2kit.testing.peek(app, LLMExtractor)` returns `RealLLM` before any `async with` block
- **WHEN** a test enters `async with a2kit.testing.client(app) as c:`, calls `c.override(LLMExtractor, FakeLLM())`, and the block exits normally
- **THEN** after the block, `a2kit.testing.peek(app, LLMExtractor)` returns the original `RealLLM` instance (or re-resolves the original singleton factory if it had not been materialised)

#### Scenario: Override is restored on exceptional exit

- **WHEN** a test enters the `async with` block, calls `c.override(T, fake)`, and the block exits due to an exception raised inside `c.invoke(...)`
- **THEN** the App's container is restored to its pre-session state, identical to a normal exit

#### Scenario: Override of an unregistered type registers the fake fresh for the session

- **GIVEN** no provider or singleton registered for type `T`
- **WHEN** test code calls `c.override(T, fake)` and then a tool depending on `T` is invoked
- **THEN** the tool receives `fake`, and on `__aexit__` the container no longer has any registration for `T` (returns to the pre-session state where `T` was unknown)

#### Scenario: Last-write-wins within a session

- **WHEN** test code calls `c.override(T, fake1)` then `c.override(T, fake2)` within one session
- **THEN** subsequent resolutions return `fake2`, and on exit the container is restored to its pre-session state (not to `fake1`)

#### Scenario: Type-safety at the call site

- **WHEN** a test author writes `c.override(LLMExtractor, "not an extractor")`
- **THEN** mypy / pyright / ty reports an argument-type error on the second argument without any `# type: ignore` being involved

#### Scenario: Concurrent override sessions on the same App are rejected

- **GIVEN** TestClient `c1` is inside an `async with` block on `app` and has called `c1.override(T, fake)`
- **WHEN** a second TestClient `c2` enters `async with a2kit.testing.client(app) as c2:` and calls `c2.override(T, other_fake)`
- **THEN** `c2.override(...)` raises `RuntimeError` indicating an override session is already active on this App

#### Scenario: TestClient.override delegates to Container._override

- **WHEN** the source of `TestClient.override` is read after this change
- **THEN** the body delegates the three-attribute mutation to `container._override(type_, fake)` and contains no `# noqa: SLF001` lines reaching into `_providers`, `_singletons`, or `_async_factories` directly

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

