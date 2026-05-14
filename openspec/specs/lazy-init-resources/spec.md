# lazy-init-resources Specification

## Purpose
TBD - created by archiving change di-sync-and-unleak. Update Purpose after archive.
## Requirements
### Requirement: Async-opened resources are encapsulated in resource classes

**Reshaped: single convention replaces the dual-pattern.** The system SHALL document **one** canonical pattern for resources that need async initialization (database connections, browser pools, HTTP clients, LLM clients): the resource expresses its lifecycle via the standard async context manager protocol — either by implementing `__aenter__` / `__aexit__` on the class itself, or by registering an `@asynccontextmanager` generator factory via `app.provide(T, factory)`. The container SHALL enter the resource lazily on first resolution (the factory's body or the class's `__aenter__` runs once), cache the resulting instance at the registered scope, and record the cleanup callable on the scope's cleanup stack. Concurrent first-touches SHALL coalesce under a per-type `asyncio.Lock` (see `app-singletons`).

The previously-documented hand-rolled "lazy-init resource" pattern (sync `__init__`, internal `asyncio.Lock`, async `_ensure`, every method `await self._ensure()` first) SHALL be removed from supported surface. The framework SHALL NOT ship either pattern as a base class, mixin, or decorator. A static lint check SHALL flag `_ensure()` method patterns on classes registered via `app.provide(...)` and suggest the equivalent `__aenter__` shape.

#### Scenario: Class-as-async-context-manager (primary)

- **GIVEN** an app needing an async-opened `SqliteResource(settings)`
- **WHEN** the app registers `app.provide(SqliteResource)` and `SqliteResource` implements `async def __aenter__` (which performs the `aiosqlite.connect` open) and `async def __aexit__` (which closes the connection)
- **THEN** the first dispatch resolving `SqliteResource` invokes `__aenter__` exactly once and caches the resolved instance
- **AND** subsequent dispatches receive the cached instance without re-entering
- **AND** App close invokes `__aexit__` exactly once via the cleanup stack

#### Scenario: Async-context-manager factory (alternative for foreign types)

- **GIVEN** an app needing to register a third-party `httpx.AsyncClient` that the user cannot modify
- **WHEN** the app registers `app.provide(httpx.AsyncClient, http_factory)` where `http_factory` is an `@asynccontextmanager async def` that yields a constructed `AsyncClient` and closes it in `finally`
- **THEN** the first dispatch resolving `httpx.AsyncClient` runs the factory body up to `yield` exactly once and caches the yielded instance
- **AND** App close advances the generator past `yield` so its `finally` block runs exactly once

#### Scenario: Concurrent first-touches coalesce

- **GIVEN** an async-context-manager-shaped registration for `SqliteResource`
- **WHEN** ten concurrent tasks each trigger first-resolution of `SqliteResource`
- **THEN** the underlying `__aenter__` (or factory body up to `yield`) is awaited exactly once
- **AND** all ten tasks share the same resolved instance

#### Scenario: `_ensure()` pattern is flagged by lint

- **GIVEN** a class `LegacyResource` registered via `app.provide(LegacyResource)` that implements `async def _ensure(self)` called from each business method
- **WHEN** `a2kit lint static` runs
- **THEN** the lint check emits a warning naming the file, line, the `_ensure` method, and the migration recipe (move the body of `_ensure` into `__aenter__`)
- **AND** the warning is suppressible only via an explicit `# noqa: A2K0XX` with an accompanying refactor TODO or issue link

### Requirement: AppState fields stay non-Optional

App state classes that follow the resource-encapsulation pattern SHALL hold resource instances as non-`Optional` fields. The pattern explicitly forbids `state.sqlite: SqliteResource | None`. The resource handle exists from construction; only the *underlying* connection is lazy (managed by the container's first-resolve-runs-`__aenter__` rule).

#### Scenario: State construction is sync and total

- **WHEN** `build_state(settings)` is called (a sync function)
- **THEN** every resource field on the returned `AppState` is populated with a constructed resource instance
- **AND** no field is `None`

### Requirement: No framework primitive for the pattern

Neither the class-as-async-context-manager path nor the `@asynccontextmanager` factory path SHALL be shipped as a framework-specific base class, mixin, or decorator inside `a2kit`. Specifically, the framework SHALL NOT introduce `@app.async_resource`, `@app.lazy`, `LazyResource`, `AsyncResource`, or any sibling name. The framework provides the surface (`app.provide(T, factory)`, scope-aware cleanup stacks, lock-coalesced first-touch); the lifecycle is expressed via standard Python protocols.

#### Scenario: No `LazyResource` symbol

- **WHEN** `from a2kit import LazyResource` is attempted
- **THEN** the import fails (the symbol does not exist)

#### Scenario: No `async_resource` decorator

- **WHEN** code attempts `@app.async_resource(SqliteResource)` or `from a2kit import async_resource`
- **THEN** the attribute does not exist on `App` and the import fails
- **AND** the documented async-resource path is `app.provide(SqliteResource)` with `__aenter__`/`__aexit__` on the class, or `app.provide(SqliteResource, factory)` with an `@asynccontextmanager` factory

