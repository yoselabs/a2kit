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

#### Scenario: log capture is structured by default

- **WHEN** a tool calls `await a2kit.ldd.info(ctx, "starting", batch=1)`
- **THEN** `client.logs[-1]` is a `LogLine` with `level="info"`, `message="starting"`, `fields={"batch": 1}`, `elapsed_ms` set

#### Scenario: rendered logs available via logs_text property

- **GIVEN** the same call
- **WHEN** the test reads `client.logs_text[-1]`
- **THEN** the value matches `[ +\d+\.\d{3} INFO    ] starting batch=1`

#### Scenario: typed reports captured as values

- **WHEN** a tool calls `await report(ctx, BatchReport(batch=1, accepted=5))`
- **THEN** `client.reports` contains the `BatchReport` instance unchanged

## REMOVED Requirements

### Requirement: (legacy) Implementation backed by StderrToolContext subclass

**Reason for removal**: the legacy implementation
(`_CapturingContext(StderrToolContext)`) structurally hid CLI-vs-MCP
divergence; the kwarg-on-info crash that motivated
`field-logging-via-ldd` was invisible to every test using this
client. The replacement implementation routes through the real
FastMCP in-memory transport so any Context-shape divergence between
CLI and MCP is observable in tests.

**Migration**: public API unchanged. Tests that assert on the
string-rendered form of `client.logs` migrate to `client.logs_text`;
tests that prefer structured assertions read `client.logs[i].level`,
`.message`, `.fields`, `.elapsed_ms`.
