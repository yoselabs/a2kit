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

The system SHALL allow multiple `App` instances to coexist in one process with fully isolated app-scope caches, lifecycle, containers, and LDD state.

#### Scenario: two Apps each have their own app-scope cache

- **WHEN** two `App` instances each register `app.provide(AppState)` with distinct factories
- **THEN** resolving `AppState` on App-A and App-B returns two different instances, neither shared

#### Scenario: lifecycle runs per-App

- **WHEN** App-A and App-B are each entered (`async with app:`) and each runs a tool
- **THEN** App-A's lifecycle and resource entry are scoped to App-A; App-B's are scoped to App-B; no cross-firing. There is no `@on_startup` decorator — lifecycle is the async-context-manager protocol plus lazy first-use resource entry.

### Requirement: Error envelope for unhandled tool exceptions

The system SHALL produce a documented error envelope when a tool body raises an exception other than `CancelledError`. The envelope contract on the **MCP wire** SHALL be owned by a2kit and SHALL NOT depend on FastMCP's `mask_error_details` flag or any other FastMCP-internal masking behavior.

When a tool body or its wrapper chain raises an exception that is not `FastMCPError` (or subclass), not `asyncio.CancelledError`, not `KeyboardInterrupt`, not `SystemExit`, and not a `BaseExceptionGroup` containing only `CancelledError`s, the MCP runtime SHALL emit a response with `isError: true` whose `content[0].text` is a JSON-encoded payload with at minimum:

- `class`: the unqualified Python class name of the exception (`type(exc).__name__`)
- `message`: the result of `str(exc)`

When `app.config.debug` resolves `True` (env `A2KIT_DEBUG=true` or `A2kitConfig(debug=True)` per ADR 0022), the payload SHALL additionally include:

- `traceback`: the result of `traceback.format_exc()` at the point of catch

`fastmcp.exceptions.FastMCPError` and subclasses (including author-raised `ToolError`) SHALL propagate unwrapped so author-shaped error messages reach the wire on FastMCP's own path. `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit` SHALL propagate unwrapped (they are `BaseException` siblings outside the catch scope). A `BaseExceptionGroup` containing only `CancelledError`s SHALL propagate unwrapped.

The CLI transport is unchanged: exceptions surface as `error: <message>` on stderr (with traceback when `app.config.debug` resolves `True`) and a non-zero process exit code.

#### Scenario: MCP path emits structured payload

- **GIVEN** a tool `async def t() -> None` whose body raises `ValueError("bad input")`
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))` with `app.config.debug == False`
- **THEN** the response has `isError=True`
- **AND** `json.loads(response.content[0].text) == {"class": "ValueError", "message": "bad input"}`

#### Scenario: debug flag includes traceback in MCP envelope

- **GIVEN** the same tool with `app.config.debug == True` (set via `A2KIT_DEBUG=true` or `A2kitConfig(debug=True)`)
- **WHEN** the tool is invoked over MCP
- **THEN** the JSON payload contains keys `class`, `message`, and `traceback`
- **AND** the `traceback` value contains the line `"ValueError: bad input"`

#### Scenario: CLI path exits non-zero with traceback to stderr

- **WHEN** a tool body raises during CLI invocation
- **THEN** the process exits with non-zero status
- **AND** the traceback appears on stderr

#### Scenario: Author-raised ToolError passes through unwrapped

- **GIVEN** a tool body `raise ToolError("permission denied")`
- **WHEN** invoked over MCP with `app.config.debug == False`
- **THEN** the response has `isError=True`
- **AND** `response.content[0].text == "permission denied"` (NOT JSON-wrapped)

#### Scenario: CancelledError propagates unwrapped

- **GIVEN** a tool body `raise asyncio.CancelledError()`
- **WHEN** invoked over MCP
- **THEN** cancellation surfaces to the client; the server does NOT emit a structured-error envelope for cancellation

#### Scenario: Envelope is FastMCP-independent

- **GIVEN** the rule has been refactored to not rely on FastMCP's `mask_error_details` flag
- **WHEN** a tool raises any non-FastMCP exception
- **THEN** a2kit produces the envelope payload directly, independently of any FastMCP-internal masking behavior

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

The system SHALL reserve the `_meta.*` tool-name prefix for framework-internal protocol tools and SHALL surface those tools differently per transport.

On the MCP transport:

- `_meta.*` tools SHALL be excluded from the default `list_tools` result.
- `_meta.*` tools SHALL NOT be callable via the MCP `call_tool` wire. An MCP client invoking `_meta.health` by exact name receives a `NotFoundError`. The CLI is the supported surface for operators who need to invoke them.

On the CLI transport:

- `_meta.*` tools SHALL appear in `<app> --help` output under a `_meta` subcommand group, discoverable to human operators.

At registration time (whether via decoration or via `build_mcp_server`'s tool loop):

- A user tool whose resolved name starts with `_meta.` and which was not registered through a2kit's own internal builders SHALL be rejected with a typed error (`ValueError`) naming the reserved namespace.

The synthetic `_meta.health` tool exists only on Apps that have at least one `@app.health_check` registration. The framework does not accept an `App(health_tool=True)` constructor keyword — it does not exist; `App(...)` with that keyword raises `TypeError`.

#### Scenario: MCP default list_tools omits _meta tools

- **WHEN** an MCP client calls `list_tools` against an app that has at least one `@app.health_check` registration, with no opt-in flag
- **THEN** the returned tool list does not include any tool whose name starts with `_meta.`

#### Scenario: MCP direct invocation by name is rejected for _meta tools

- **WHEN** an MCP client calls `_meta.health` by exact name on an app that has at least one `@app.health_check` registration
- **THEN** the dispatcher raises `NotFoundError` (or the FastMCP-3 equivalent) and the tool body is not executed

#### Scenario: CLI surfaces _meta tools under a discoverable group

- **WHEN** a user runs `<app> --help` on an app with at least one `_meta.*` tool registered
- **THEN** the help output documents a `_meta` subcommand group whose entries include each `_meta.*` tool

#### Scenario: User registration with reserved name is rejected at build time

- **WHEN** a tool with a `_meta.*` name is presented to `build_mcp_server` without the a2kit-internal sentinel in its metadata
- **THEN** `build_mcp_server` raises `ValueError` naming the reserved namespace and pointing at the documented contract

### Requirement: LDD primitives require an active tool dispatch

LDD primitives (`a2kit.log.info` / `report` / `log` / `debug` / `info` / `warning` / `error` and `EventRegistry.emit_typed`) SHALL be callable from any code path reached during an active tool dispatch — that is, while the dispatcher's ambient `ldd_state_for_call` scope is in effect for the current task. This includes:

- the tool body itself (whether or not it declares `ctx`),
- helper functions and coroutines it calls directly or indirectly,
- async tasks spawned via `asyncio.gather`, `create_task`, or `TaskGroup` (Python's `contextvars` copy-on-task semantics carry the ambient ctx into the spawned task), and
- DI factories (including `app.provide` async factories) instantiated *lazily during dispatch* as a dependency of the running tool.

The primitives SHALL NOT be callable from any pre-dispatch context: imperative startup code, module-import-time code, or any other code path running outside an active `ldd_state_for_call` scope. (There are no `on_startup` / `on_shutdown` lifecycle hooks — those decorators do not exist on `App`.) Violations SHALL raise `AmbientContextMissing` (Mode A) rather than silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause stating this rule, so downstream apps know where LDD telemetry is and is not legal.

#### Scenario: tool body usage is legal regardless of ctx declaration

- **GIVEN** two tools, one declaring `ctx: a2kit.ToolContext` and one not, both calling `await a2kit.log.info("x", k=1)` in their bodies
- **WHEN** each tool runs under any transport
- **THEN** both events are delivered to sinks and no exception is raised
- **AND** the wire emission (MCP log notification or CLI stderr line) fires for both

#### Scenario: pre-dispatch usage still raises

- **GIVEN** imperative startup code calling `await a2kit.log.info("booting")` before any tool dispatch (outside any `ldd_state_for_call` scope)
- **WHEN** that code runs
- **THEN** it surfaces `AmbientContextMissing` (Mode A)

#### Scenario: lazy app-scope factory during dispatch is legal

- **GIVEN** an async app-scope factory registered via `app.provide(Pool, async_factory)` where `async_factory` body calls `await a2kit.log.info("pool initializing")`
- **AND** the resource has not yet been instantiated when a tool dispatch begins
- **WHEN** the tool resolves `Pool` for the first time during its dispatch, causing `async_factory` to run inside the dispatch's ambient ctx scope
- **THEN** the LDD primitive in the factory body SHALL succeed and emit the event normally

### Requirement: `AmbientContextMissing` distinguishes pre-dispatch vs missing-ctx-param failure modes

The library SHALL raise `AmbientContextMissing` only when an LDD
primitive is called outside an active tool dispatch (Mode A). Inside
any framework dispatch, the ambient `ctx` is guaranteed non-None —
the dispatcher's wrapper synthesizes it for every dispatched tool,
regardless of whether the tool's signature declares
`ctx: a2kit.ToolContext`.

The `AmbientContextMissing.MODE_MISSING_CTX_PARAM` constant SHALL be
retained for backward-compatible external reference but SHALL be
documented as historical: no framework code path raises it. Tools
whose body does not declare `ctx` no longer trip Mode B — LDD
primitives emit through the framework-synthesized ambient ctx.

Mode A (`no active dispatch`) continues to fire for module-import-time
calls, pre-dispatch lifecycle code (`on_startup` / `on_shutdown`),
and orphan task contexts.

This change aligns the framework with LDD's log-driven-development
purpose: structured log emission (sink-side) is the primary value;
wire-side emission is incidental and never gates whether the
primitive succeeds.

#### Scenario: Mode A — pre-dispatch call still raises

- **GIVEN** code at module top level calling `a2kit.log.info("x", k=1)`
- **WHEN** the module is imported
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains "called outside an active tool dispatch"

#### Scenario: Tool without ctx param inside dispatch — no raise

- **GIVEN** a tool `async def fetch(*, url: str) -> dict: await a2kit.log.info("fetch", url=url); return {}`
- **WHEN** the tool runs under any transport (MCP, CLI, TestClient)
- **THEN** `AmbientContextMissing` is NOT raised
- **AND** the event is captured by all configured sinks
- **AND** the wire side emits via the synthesized ambient ctx (MCP log notification or CLI stderr line)

#### Scenario: MODE_MISSING_CTX_PARAM constant preserved

- **WHEN** external code references `AmbientContextMissing.MODE_MISSING_CTX_PARAM`
- **THEN** the attribute resolves to a string value
- **AND** no framework code path raises with that mode

