# in-process-test-client — rebuild-test-client-on-real-context delta

## MODIFIED Requirements

### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async
context manager that runs the **real FastMCP in-memory transport**
in-process and exposes capture surfaces for assertions. The test
client SHALL build a `FastMCP` server via `build_mcp_server(app)`
and connect to it through `fastmcp.Client(transport=server, ...)`,
exercising the same dispatch path production MCP transport uses.

The test client SHALL NOT subclass `StderrToolContext` or otherwise
construct a CLI-shaped fake of the runtime Context.

#### Scenario: ctx received by tools is a real fastmcp.Context

- **WHEN** a tool's body runs under `async with a2kit.testing.client(app)`
- **THEN** the ctx argument satisfies `isinstance(ctx, fastmcp.Context)`
- **AND** `isinstance(ctx, StderrToolContext)` is False

#### Scenario: invoke runs the same code path as production dispatch

- **WHEN** a test calls `await client.invoke("tasks.create", name="x")` on an app with `TasksRouter`
- **THEN** the dispatcher resolves DI, runs decorator processing, executes the tool body, and returns the value the tool returned, with the dispatch routed through the real FastMCP server

#### Scenario: lifecycle hooks fire around the test session

- **WHEN** a test enters `async with a2kit.testing.client(app) as c:` and exits the block
- **THEN** registered `@app.on_startup` handlers run before the first invoke and `@app.on_shutdown` handlers run after the block exits, exactly once each

### Requirement: Event and progress capture

The test client SHALL capture every event, progress update, log call, and report emitted via `ctx` during a tool invocation, exposing them as ordered lists. Log capture SHALL surface as structured `LogLine` entries (level, message, fields, elapsed_ms); a derived `logs_text` property renders each via `format_ldd_line` for tests that need the wire-format string.

#### Scenario: events captured with payload and elapsed_ms

- **WHEN** a tool calls `await event(ctx, "import.started", n=10)` and later `await event(ctx, "import.complete", count=10)`
- **THEN** `client.events` contains both entries in order, each with `name`, `payload`, and `elapsed_ms` fields

#### Scenario: progress captured as (current, total) tuples

- **WHEN** a tool calls `await ctx.report_progress(5, total=10)`
- **THEN** `client.progress[-1] == (5, 10)`

#### Scenario: log capture as dicts

- **WHEN** a tool calls `await a2kit.ldd.info("starting", batch=1)`
- **THEN** `client.logs[-1]` is a dict with `level` (uppercase shorthand like `"INFO"`), `msg`, `fields` (`{"batch": 1}`), and `elapsed_ms` keys

#### Scenario: typed reports captured as dicts

- **WHEN** a tool calls `await a2kit.ldd.report(BatchReport(batch=1, accepted=5))`
- **THEN** `client.reports[-1]` is a dict with `type` (the class name), `body` (`model_dump()` payload), and `elapsed_ms` keys

#### Scenario: wire payload prefixes a2kit-internal keys to dodge LogRecord collisions

- **GIVEN** an `a2kit.ldd.event("evt", payload={"k": 1})` call on the MCP transport
- **WHEN** the server-side ctx.log call passes through FastMCP's `_log_to_server_and_client` (which calls `to_client_logger.log(..., extra=...)`)
- **THEN** the `extra` dict contains `a2kit_kind`, `a2kit_name`, `a2kit_payload`, `a2kit_elapsed_ms` — none of which collide with Python `LogRecord` reserved attributes
- **AND** the client-side `log_handler` un-prefixes these back to the public capture shape (`{"name", "payload", "elapsed_ms"}`)

## ADDED Requirements

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

The test client SHALL re-enable the `_meta` tag on the server it builds so hidden protocol-meta tools (e.g. `_meta.health`) are invocable via `invoke()`. Production MCP transport hides them via `server.disable(tags={"_meta"})`; the test client opts back in so test authors can probe health and other meta surfaces.

#### Scenario: _meta.health invocable through test client

- **GIVEN** `App("a", health_tool=True)`
- **WHEN** the test calls `await client.invoke("_meta.health")`
- **THEN** the call succeeds and the result includes the aggregated health payload

<!--
  Removed-requirement note: the legacy `_CapturingContext(StderrToolContext)`
  implementation was already retired from the in-process-test-client spec by
  the time this change archived. The "Implementation backed by StderrToolContext
  subclass" header is not present in the canonical spec, so no REMOVED clause
  is emitted here.

  Migration carried over: public API unchanged for events/reports/progress/logs
  capture shapes (preserved as dicts/tuples). Tests asserting on raw Python
  class identity of `invoke()` return values migrate to field-wise or
  `model_dump()` comparison. Tests catching tool-body Python exceptions migrate
  to catching `fastmcp.exceptions.ToolError` and parsing the JSON envelope.
-->

