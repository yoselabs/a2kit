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

