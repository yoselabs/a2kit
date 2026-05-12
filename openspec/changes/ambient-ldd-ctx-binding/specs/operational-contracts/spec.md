## ADDED Requirements

### Requirement: LDD primitives require an active tool dispatch

The library's LDD primitives (`a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, and `EventRegistry.emit_typed`) SHALL be callable only from inside a tool body or from a coroutine/task transitively spawned by a tool body during its lifetime. Lifecycle hooks (`on_startup`, `on_shutdown`), DI factory functions, module-level code, and any code path that runs outside an active `ldd_state_for_call` scope SHALL NOT call these primitives. Violations SHALL raise `AmbientContextMissing` rather than silently no-op.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause stating this rule, so downstream apps know where LDD telemetry is and is not legal.

#### Scenario: tool body usage is legal

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> None: await a2kit.ldd.event("x", k=1)`
- **WHEN** the tool runs under any transport (MCP, CLI, TestClient)
- **THEN** the event is delivered and no exception is raised

#### Scenario: lifecycle hook usage raises

- **GIVEN** an `on_startup` hook calling `await a2kit.ldd.info("booting")`
- **WHEN** the app starts up
- **THEN** the lifecycle dispatch surfaces `AmbientContextMissing`

#### Scenario: contract documented in OPERATIONAL_CONTRACTS.md

- **WHEN** a reader opens `OPERATIONAL_CONTRACTS.md`
- **THEN** there is a section naming the LDD primitives and stating that they require an active tool dispatch
