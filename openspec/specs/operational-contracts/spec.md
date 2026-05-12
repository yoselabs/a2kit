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

### Requirement: The `_meta.*` tool namespace is closed and split per transport

The system SHALL reserve the `_meta.*` tool-name prefix for
framework-internal protocol tools and SHALL surface those tools
differently per transport.

On the MCP transport:

- `_meta.*` tools SHALL be excluded from the default `list_tools`
  result.
- `_meta.*` tools SHALL NOT be callable via the MCP `call_tool`
  wire. An MCP client invoking `_meta.health` by exact name
  receives a `NotFoundError`. The CLI is the supported surface
  for operators who need to invoke them.

On the CLI transport:

- `_meta.*` tools SHALL appear in `<app> --help` output under a
  `_meta` subcommand group, discoverable to human operators.

At registration time (whether via decoration or via
`build_mcp_server`'s tool loop):

- A user tool whose resolved name starts with `_meta.` and which
  was not registered through a2kit's own internal builders SHALL
  be rejected with a typed error (`ValueError`) naming the reserved
  namespace.

#### Scenario: MCP default list_tools omits _meta tools

- **WHEN** an MCP client calls `list_tools` against an app
  constructed with `health_tool=True` and no opt-in flag
- **THEN** the returned tool list does not include any tool whose
  name starts with `_meta.`

#### Scenario: MCP direct invocation by name is rejected for _meta tools

- **WHEN** an MCP client calls `_meta.health` by exact name on
  an app constructed with `health_tool=True`
- **THEN** the dispatcher raises `NotFoundError` (or the
  FastMCP-3 equivalent) and the tool body is not executed

#### Scenario: CLI surfaces _meta tools under a discoverable group

- **WHEN** a user runs `<app> --help` on an app with at least one
  `_meta.*` tool registered
- **THEN** the help output documents a `_meta` subcommand group
  whose entries include each `_meta.*` tool

#### Scenario: User registration with reserved name is rejected at build time

- **WHEN** a tool with a `_meta.*` name is presented to
  `build_mcp_server` without the a2kit-internal sentinel in its
  metadata
- **THEN** `build_mcp_server` raises `ValueError` naming the
  reserved namespace and pointing at the documented contract

### Requirement: LDD primitives require an active tool dispatch

The library's LDD primitives (`a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, and `EventRegistry.emit_typed`) SHALL be callable only from code paths reached during an active tool dispatch — that is, while the dispatcher's ambient `ldd_state_for_call` scope is in effect for the current task. This includes:

- the tool body itself,
- helper functions and coroutines it calls directly or indirectly,
- async tasks spawned via `asyncio.gather`, `create_task`, or `TaskGroup`
  (Python's `contextvars` copy-on-task semantics carry the ambient ctx
  into the spawned task), and
- DI factories (including `app.singleton` async factories) instantiated
  *lazily during dispatch* as a dependency of the running tool.

The primitives SHALL NOT be callable from any pre-dispatch context:
lifecycle hooks (`on_startup`, `on_shutdown`), module-import-time code,
or any other code path running outside an active `ldd_state_for_call`
scope. Violations SHALL raise `AmbientContextMissing` rather than
silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause
stating this rule, so downstream apps know where LDD telemetry is and is
not legal.

#### Scenario: tool body usage is legal

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> None: await a2kit.ldd.event("x", k=1)`
- **WHEN** the tool runs under any transport (MCP, CLI, TestClient)
- **THEN** the event is delivered and no exception is raised

#### Scenario: lifecycle hook usage raises

- **GIVEN** an `on_startup` hook calling `await a2kit.ldd.info("booting")`
- **WHEN** the app starts up
- **THEN** the lifecycle dispatch surfaces `AmbientContextMissing`

#### Scenario: lazy singleton factory during dispatch is legal

- **GIVEN** an async singleton factory registered via
  `app.singleton(Pool, async_factory)` where `async_factory` body calls
  `await a2kit.ldd.info("pool initializing")`
- **AND** the singleton has not yet been instantiated when a tool dispatch begins
- **WHEN** the tool resolves `Pool` for the first time during its dispatch,
  causing `async_factory` to run inside the dispatch's ambient ctx scope
- **THEN** the LDD primitive in the factory body SHALL succeed and emit
  the event normally; `AmbientContextMissing` SHALL NOT be raised

#### Scenario: contract documented in OPERATIONAL_CONTRACTS.md

- **WHEN** a reader opens `OPERATIONAL_CONTRACTS.md`
- **THEN** there is a section naming the LDD primitives and stating that
  they require an active tool dispatch, and explicitly clarifying that
  lazy DI factories instantiated during dispatch ARE legal call sites
  while lifecycle hooks, module init, and other pre-dispatch contexts
  are NOT

