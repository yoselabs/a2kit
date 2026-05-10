# operational-contracts Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: Cancellation propagates from transport to tool body

The system SHALL propagate `asyncio.CancelledError` from transport disconnect (MCP) or SIGINT (CLI) through to the tool body without intercepting it.

#### Scenario: tool body sees CancelledError on transport disconnect

- **WHEN** an MCP client disconnects mid-tool-execution and the dispatch task is cancelled
- **THEN** the tool's coroutine raises `asyncio.CancelledError` at its next `await` point and the dispatcher does not swallow it

#### Scenario: SIGINT during CLI invocation cancels the running tool

- **WHEN** the user presses Ctrl-C during `a2kit.run(app)` while a tool is awaiting
- **THEN** the tool body sees `CancelledError` and any cleanup `finally` blocks run before process exit

### Requirement: Multi-App isolation

The system SHALL allow multiple `App` instances to coexist in one process with fully isolated singletons, lifecycle handlers, containers, and LDD state.

#### Scenario: two Apps each have their own singleton cache

- **WHEN** two `App` instances each register `app.singleton(AppState)` with distinct factories
- **THEN** resolving `AppState` on App-A and App-B returns two different instances, neither shared

#### Scenario: lifecycle handlers run per-App

- **WHEN** App-A and App-B each register `@on_startup` handlers and both apps run a tool
- **THEN** App-A's startup runs once for App-A's first tool; App-B's startup runs once for App-B's first tool; no cross-firing

### Requirement: Error envelope for unhandled tool exceptions

The system SHALL produce a documented error envelope when a tool body raises an exception other than `CancelledError`.

#### Scenario: MCP path emits JsonRpcError

- **WHEN** a tool body raises `ValueError("bad input")` during MCP dispatch
- **THEN** the dispatcher emits a `JsonRpcError` with `code=-32603` and `message` containing the exception's `str()` repr

#### Scenario: CLI path exits non-zero with traceback to stderr

- **WHEN** a tool body raises during `a2kit.run(app)` invocation
- **THEN** the process exits with non-zero status and the traceback appears on stderr

#### Scenario: debug flag includes traceback in MCP envelope

- **WHEN** `App(..., debug=True)` is set and a tool body raises
- **THEN** the `JsonRpcError.data.traceback` field contains the full traceback string

### Requirement: Per-tool timeouts are not built-in (recommended pattern documented)

The system SHALL document that per-tool timeouts are not a framework feature and recommend the `anyio.fail_after` pattern.

#### Scenario: documentation references the recommended pattern

- **WHEN** a consumer reads the operational-contracts documentation
- **THEN** the docs include a code example using `async with anyio.fail_after(60): ...` inside a tool body

### Requirement: Streaming output deferred

The system SHALL document that streaming responses (chunked output) are not supported in v0.25 and that tool returns are atomic.

#### Scenario: documentation states atomic-only

- **WHEN** a consumer reads the operational-contracts documentation
- **THEN** the docs state explicitly that tool returns are atomic in v0.25 and reference a future change for streaming

