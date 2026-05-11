# lazy-init-resources Specification

## Purpose
TBD - created by archiving change di-sync-and-unleak. Update Purpose after archive.

## Requirements
### Requirement: Async-opened resources are encapsulated in resource classes

The system SHALL document and the framework SHALL support a "lazy-init resource" pattern for apps that need async resource initialization (database connections, browser pools, HTTP clients, etc.). The pattern: a resource class with synchronous construction, an internal `asyncio.Lock`, an async `_ensure` (or named equivalent) accessor that opens the underlying resource on first call, async business methods that await `_ensure` internally, and an idempotent async `close` method.

#### Scenario: Resource opens on first use

- **GIVEN** a resource class `SqliteResource(settings)` whose `__init__` is synchronous and does no I/O
- **WHEN** `await resource.execute("SELECT 1")` is called the first time
- **THEN** the resource opens its underlying `aiosqlite` connection under its internal lock, then runs the SQL

#### Scenario: Concurrent first-touches coalesce

- **GIVEN** the same resource instance
- **WHEN** ten concurrent tasks each call an async method that triggers the underlying open
- **THEN** the underlying open is awaited exactly once
- **AND** all ten tasks share the same opened handle

#### Scenario: Close is idempotent

- **WHEN** `await resource.close()` is called twice
- **THEN** the second call is a no-op and does not raise

### Requirement: AppState fields stay non-Optional

App state classes that follow the lazy-init pattern SHALL hold resource instances as non-`Optional` fields. The pattern explicitly forbids `state.sqlite: SqliteResource | None`. The resource handle exists from construction; only the *underlying* connection is lazy.

#### Scenario: State construction is sync and total

- **WHEN** `build_state(settings)` is called (a sync function)
- **THEN** every resource field on the returned `AppState` is populated with a constructed resource instance
- **AND** no field is `None`

### Requirement: Cleanup goes through `@on_shutdown`

The pattern SHALL document `@app.on_shutdown` as the cleanup site for resources. Each registered shutdown handler takes `state: AppState` (via DI) and awaits the resource's `close()` method.

#### Scenario: Shutdown closes resources

- **GIVEN** an app with `@on_shutdown async def _close(state: AppState): await state.sqlite.close()`
- **WHEN** the lifecycle dispatches shutdown
- **THEN** the resource's `close` runs once and the underlying connection is released

### Requirement: Optional fail-fast warm-up via `@on_startup`

The pattern SHALL document an optional `@app.on_startup` warm-up that triggers `_ensure` early to surface configuration errors at startup rather than at first tool call.

#### Scenario: Warm-up triggers init

- **GIVEN** an app with `@on_startup async def _warm(state: AppState): await state.sqlite._ensure()`
- **WHEN** the lifecycle dispatches startup
- **THEN** the underlying `aiosqlite.connect` is awaited before any tool is served

### Requirement: No framework primitive for the pattern

The pattern SHALL be documented but NOT shipped as a base class, mixin, or decorator inside `a2kit`. Resource classes are consumer-owned. The framework provides the surface (sync DI, DI-aware lifecycle) on which the pattern composes; it does not own the pattern itself.

#### Scenario: No `LazyResource` symbol

- **WHEN** `from a2kit import LazyResource` is attempted
- **THEN** the import fails (the symbol does not exist)
