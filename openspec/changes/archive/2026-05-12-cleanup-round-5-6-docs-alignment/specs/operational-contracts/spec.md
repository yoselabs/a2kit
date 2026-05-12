## MODIFIED Requirements

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
