## MODIFIED Requirements

### Requirement: Multi-App isolation

The system SHALL allow multiple `App` instances to coexist in one process with fully isolated app-scope caches, lifecycle, containers, and LDD state.

#### Scenario: two Apps each have their own app-scope cache

- **WHEN** two `App` instances each register `app.provide(AppState)` with distinct factories
- **THEN** resolving `AppState` on App-A and App-B returns two different instances, neither shared

#### Scenario: lifecycle runs per-App

- **WHEN** App-A and App-B are each entered (`async with app:`) and each runs a tool
- **THEN** App-A's lifecycle and resource entry are scoped to App-A; App-B's are scoped to App-B; no cross-firing. There is no `@on_startup` decorator — lifecycle is the async-context-manager protocol plus lazy first-use resource entry.

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

LDD primitives (`a2kit.ldd.event` / `report` / `log` / `debug` / `info` / `warning` / `error` and `EventRegistry.emit_typed`) SHALL be callable from any code path reached during an active tool dispatch — that is, while the dispatcher's ambient `ldd_state_for_call` scope is in effect for the current task. This includes:

- the tool body itself (whether or not it declares `ctx`),
- helper functions and coroutines it calls directly or indirectly,
- async tasks spawned via `asyncio.gather`, `create_task`, or `TaskGroup` (Python's `contextvars` copy-on-task semantics carry the ambient ctx into the spawned task), and
- DI factories (including `app.provide` async factories) instantiated *lazily during dispatch* as a dependency of the running tool.

The primitives SHALL NOT be callable from any pre-dispatch context: imperative startup code, module-import-time code, or any other code path running outside an active `ldd_state_for_call` scope. (There are no `on_startup` / `on_shutdown` lifecycle hooks — those decorators do not exist on `App`.) Violations SHALL raise `AmbientContextMissing` (Mode A) rather than silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause stating this rule, so downstream apps know where LDD telemetry is and is not legal.

#### Scenario: tool body usage is legal regardless of ctx declaration

- **GIVEN** two tools, one declaring `ctx: a2kit.ToolContext` and one not, both calling `await a2kit.ldd.event("x", k=1)` in their bodies
- **WHEN** each tool runs under any transport
- **THEN** both events are delivered to sinks and no exception is raised
- **AND** the wire emission (MCP log notification or CLI stderr line) fires for both

#### Scenario: pre-dispatch usage still raises

- **GIVEN** imperative startup code calling `await a2kit.ldd.info("booting")` before any tool dispatch (outside any `ldd_state_for_call` scope)
- **WHEN** that code runs
- **THEN** it surfaces `AmbientContextMissing` (Mode A)

#### Scenario: lazy app-scope factory during dispatch is legal

- **GIVEN** an async app-scope factory registered via `app.provide(Pool, async_factory)` where `async_factory` body calls `await a2kit.ldd.info("pool initializing")`
- **AND** the resource has not yet been instantiated when a tool dispatch begins
- **WHEN** the tool resolves `Pool` for the first time during its dispatch, causing `async_factory` to run inside the dispatch's ambient ctx scope
- **THEN** the LDD primitive in the factory body SHALL succeed and emit the event normally
