# operational-contracts

## MODIFIED Requirements

### Requirement: LDD primitives require an active tool dispatch

LDD primitives (`a2kit.log.info` / `report` / `log` / `debug` / `info` / `warning` / `error` and `EventRegistry.emit_typed`) SHALL be callable from any code path reached during an active tool dispatch — that is, while the dispatcher's ambient `ldd_state_for_call` scope is in effect for the current task. This includes:

- the tool body itself (whether or not it declares `ctx`),
- helper functions and coroutines it calls directly or indirectly,
- async tasks spawned via `asyncio.gather`, `create_task`, or `TaskGroup` (Python's `contextvars` copy-on-task semantics carry the ambient ctx into the spawned task), and
- DI factories (including `app.provide` async factories) instantiated *lazily during dispatch* as a dependency of the running tool.

The primitives SHALL NOT be callable from any pre-dispatch context: imperative startup code, module-import-time code, or any other code path running outside an active `ldd_state_for_call` scope. (There are no `on_startup` / `on_shutdown` lifecycle hooks — those decorators do not exist on `App`.) Violations SHALL raise `RequestScopeMissing` rather than silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause stating this rule, so downstream apps know where LDD telemetry is and is not legal.

#### Scenario: tool body usage is legal regardless of ctx declaration

- **GIVEN** two tools, one declaring `ctx: a2kit.ToolContext` and one not, both calling `await a2kit.log.info("x", k=1)` in their bodies
- **WHEN** each tool runs under any transport
- **THEN** both events are delivered to sinks and no exception is raised
- **AND** the wire emission (MCP log notification or CLI stderr line) fires for both

#### Scenario: pre-dispatch usage still raises

- **GIVEN** imperative startup code calling `await a2kit.log.info("booting")` before any tool dispatch (outside any `ldd_state_for_call` scope)
- **WHEN** that code runs
- **THEN** it surfaces `RequestScopeMissing`

#### Scenario: lazy app-scope factory during dispatch is legal

- **GIVEN** an async app-scope factory registered via `app.provide(Pool, async_factory)` where `async_factory` body calls `await a2kit.log.info("pool initializing")`
- **AND** the resource has not yet been instantiated when a tool dispatch begins
- **WHEN** the tool resolves `Pool` for the first time during its dispatch, causing `async_factory` to run inside the dispatch's ambient ctx scope
- **THEN** the LDD primitive in the factory body SHALL succeed and emit the event normally

## REMOVED Requirements

### Requirement: `AmbientContextMissing` distinguishes pre-dispatch vs missing-ctx-param failure modes

**Reason**: `AmbientContextMissing` and its `MODE_NO_DISPATCH` /
`MODE_MISSING_CTX_PARAM` constants are removed (no backward compatibility,
no migration hints). Out-of-dispatch emission raises `RequestScopeMissing`
(covered by "LDD primitives require an active tool dispatch"); emission from a
tool that omits its `ctx` parameter does not raise, because the dispatcher
synthesizes the ambient ctx. There is no longer a class with failure-mode
constants to document.
