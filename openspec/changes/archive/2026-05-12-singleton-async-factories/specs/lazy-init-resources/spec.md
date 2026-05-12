## MODIFIED Requirements

### Requirement: Async-opened resources are encapsulated in resource classes

The system SHALL document `App.singleton(T, async_factory)` as the **primary** path for resources that need async initialization (database connections, browser pools, HTTP clients, LLM clients). An app SHOULD register such resources with an `async def` factory whose body performs the open and returns a constructed instance; the container awaits the factory exactly once on first resolution and caches the result, with concurrent first-touches coalesced under a per-type lock (see the `app-singletons` capability). The previously-documented hand-rolled "lazy-init resource" class pattern (sync `__init__`, internal `asyncio.Lock`, async `_ensure`, every method `await self._ensure()` first) is repositioned as an **escape hatch** for resources that legitimately need per-method re-entry guards (e.g. reconnect-on-failure semantics, partial pool re-initialization, resources whose `close()` lifecycle is not aligned with `@on_shutdown`). The framework SHALL NOT ship either pattern as a base class, mixin, or decorator.

#### Scenario: Primary path uses async-factory singleton

- **GIVEN** an app needing an async-opened `SqliteResource(settings)`
- **WHEN** the app registers `app.singleton(SqliteResource, build_sqlite_async)` where `build_sqlite_async` is `async def` and performs the `aiosqlite.connect` open inside its body
- **THEN** `SqliteResource` is the documented, recommended way to expose the resource to tool methods via DI
- **AND** consumers do not need to hand-roll an `_ensure` accessor or internal `asyncio.Lock`

#### Scenario: Concurrent first-touches coalesce (primary path)

- **GIVEN** an async-factory singleton for `SqliteResource`
- **WHEN** ten concurrent tasks each trigger first-resolution of `SqliteResource`
- **THEN** the underlying async open is awaited exactly once
- **AND** all ten tasks share the same resolved instance

#### Scenario: Escape-hatch pattern for per-method re-entry guards

- **GIVEN** a resource that must reopen its underlying connection on transient failure and protect re-opens from concurrent callers across multiple tool dispatches
- **WHEN** the consumer chooses the hand-rolled pattern (sync `__init__`, internal `asyncio.Lock`, async `_ensure`, async business methods that await `_ensure` first, idempotent async `close`)
- **THEN** the framework supports this composition through the same DI surface (the resource class is registered via `app.singleton` or `app.provide` like any other type)
- **AND** the documentation marks this as an escape hatch, not the recommended path

#### Scenario: Close is idempotent (escape-hatch pattern)

- **WHEN** `await resource.close()` is called twice on a hand-rolled resource class
- **THEN** the second call is a no-op and does not raise

### Requirement: No framework primitive for the pattern

Neither the primary async-factory-singleton path nor the escape-hatch hand-rolled resource pattern SHALL be shipped as a base class, mixin, or decorator inside `a2kit`. Specifically, the framework SHALL NOT introduce `@app.async_resource`, `@app.lazy`, `LazyResource`, `AsyncResource`, or any sibling name. The framework provides the surface (sync DI, async-factory-aware `singleton`, DI-aware lifecycle) on which both patterns compose; it does not own either pattern itself.

#### Scenario: No `LazyResource` symbol

- **WHEN** `from a2kit import LazyResource` is attempted
- **THEN** the import fails (the symbol does not exist)

#### Scenario: No `async_resource` decorator

- **WHEN** code attempts `@app.async_resource(SqliteResource)` or `from a2kit import async_resource`
- **THEN** the attribute does not exist on `App` and the import fails
- **AND** the documented async-resource path is `app.singleton(SqliteResource, build_sqlite_async)` with an `async def` factory
