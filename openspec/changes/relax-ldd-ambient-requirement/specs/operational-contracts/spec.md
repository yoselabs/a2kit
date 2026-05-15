# operational-contracts Specification Delta

## MODIFIED Requirements

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

- **GIVEN** code at module top level calling `a2kit.ldd.event("x", k=1)`
- **WHEN** the module is imported
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains "called outside an active tool dispatch"

#### Scenario: Tool without ctx param inside dispatch — no raise

- **GIVEN** a tool `async def fetch(*, url: str) -> dict: await a2kit.ldd.event("fetch", url=url); return {}`
- **WHEN** the tool runs under any transport (MCP, CLI, TestClient)
- **THEN** `AmbientContextMissing` is NOT raised
- **AND** the event is captured by all configured sinks
- **AND** the wire side emits via the synthesized ambient ctx (MCP log notification or CLI stderr line)

#### Scenario: MODE_MISSING_CTX_PARAM constant preserved

- **WHEN** external code references `AmbientContextMissing.MODE_MISSING_CTX_PARAM`
- **THEN** the attribute resolves to a string value
- **AND** no framework code path raises with that mode

### Requirement: LDD primitives require an active tool dispatch

LDD primitives (`a2kit.ldd.event` / `report` / `log` / `debug` / `info` / `warning` / `error` and `EventRegistry.emit_typed`) SHALL be callable from any code path reached during an active tool dispatch — that is, while the dispatcher's ambient `ldd_state_for_call` scope is in effect for the current task. This includes:

- the tool body itself (whether or not it declares `ctx`),
- helper functions and coroutines it calls directly or indirectly,
- async tasks spawned via `asyncio.gather`, `create_task`, or `TaskGroup`
  (Python's `contextvars` copy-on-task semantics carry the ambient ctx
  into the spawned task), and
- DI factories (including `app.provide` async factories) instantiated
  *lazily during dispatch* as a dependency of the running tool.

The primitives SHALL NOT be callable from any pre-dispatch context:
lifecycle hooks (`on_startup`, `on_shutdown`), module-import-time code,
or any other code path running outside an active `ldd_state_for_call`
scope. Violations SHALL raise `AmbientContextMissing` (Mode A) rather
than silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit
clause stating this rule, so downstream apps know where LDD telemetry
is and is not legal.

#### Scenario: tool body usage is legal regardless of ctx declaration

- **GIVEN** two tools, one declaring `ctx: a2kit.ToolContext` and one not, both calling `await a2kit.ldd.event("x", k=1)` in their bodies
- **WHEN** each tool runs under any transport
- **THEN** both events are delivered to sinks and no exception is raised
- **AND** the wire emission (MCP log notification or CLI stderr line) fires for both

#### Scenario: lifecycle hook usage still raises

- **GIVEN** an `on_startup` hook calling `await a2kit.ldd.info("booting")`
- **WHEN** the app starts up
- **THEN** the lifecycle dispatch surfaces `AmbientContextMissing` (Mode A)

#### Scenario: lazy singleton factory during dispatch is legal

- **GIVEN** an async singleton factory registered via
  `app.provide(Pool, async_factory)` where `async_factory` body calls
  `await a2kit.ldd.info("pool initializing")`
- **AND** the singleton has not yet been instantiated when a tool dispatch begins
- **WHEN** the tool resolves `Pool` for the first time during its dispatch,
  causing `async_factory` to run inside the dispatch's ambient ctx scope
- **THEN** the LDD primitive in the factory body SHALL succeed and emit
  the event normally
