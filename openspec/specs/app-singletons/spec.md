# app-singletons Specification

## Purpose
TBD - created by archiving change app-lifecycle-and-di-ergonomics. Update Purpose after archive.
## Requirements
### Requirement: App exposes `singleton(T, factory=None)` registration

The `a2kit.App` class SHALL expose `singleton(type_: type[T], factory: Callable[..., T] | None = None)` that registers a typed factory whose result is cached on the `App` instance and shared across all dispatches that resolve `type_`. The call SHALL ALWAYS return `self` (for chaining), never a decorator. When `factory` is omitted, `type_` itself SHALL be used as the factory (class-as-factory), and the container SHALL introspect `type_.__init__` at resolve time — same semantics as `app.provide(T)`. **Factories MUST be synchronous** (`def`, not `async def`); async factories raise `ValueError` at registration time. The previous decorator form `@app.singleton(T)` SHALL be removed; the method-call form is the only path.

#### Scenario: Method form with explicit factory

- **WHEN** `app.singleton(AppState, lambda: AppState(...))` is called with a sync factory
- **THEN** `AppState` is resolvable from the container
- **AND** the factory is invoked at most once per `App` instance
- **AND** the call returns `self` for chaining

#### Scenario: Class-as-factory form

- **WHEN** `app.singleton(AppState)` is called with no second argument
- **THEN** `AppState.__init__` is used as the factory at resolve time
- **AND** dependencies of `__init__` are resolved via the container chain
- **AND** the call returns `self` for chaining

#### Scenario: Decorator form removed

- **WHEN** consumer code applies `@app.singleton(AppState)` to a factory function
- **THEN** the decoration fails (e.g., `TypeError` from attempting to call `self` as a decorator)
- **AND** the migration message points the author at the method-call form `app.singleton(AppState, build_state)`

#### Scenario: Async factory rejected

- **WHEN** `app.singleton(AppState, async_build_state)` is called with `async_build_state` being `async def`
- **THEN** `ValueError` is raised at registration naming the offending factory and pointing the user at the lazy-init resource pattern

### Requirement: Singletons resolve via the request-scoped container

A registered singleton SHALL be reachable via `container.resolve(T)` exactly like a `provide`-registered type. The container SHALL receive the cached instance on every resolve after the first. Resolution is synchronous.

#### Scenario: Singleton resolved twice returns the same instance

- **GIVEN** `app.singleton(AppState, factory)` where `factory` returns a fresh instance each time it is called
- **WHEN** the container resolves `AppState` twice (across two dispatches or two `resolve` calls)
- **THEN** both resolves return the same object
- **AND** `factory` was invoked exactly once

#### Scenario: Singleton dependency chains

- **GIVEN** `app.singleton(AppState, lambda settings: AppState(settings))` and `app.provide(Settings, load_settings)` (both sync)
- **WHEN** a tool method declares `state: AppState`
- **THEN** the container resolves `Settings` (per-dispatch), then resolves `AppState` once via the lambda
- **AND** subsequent dispatches reuse the cached `AppState` and do not re-call the factory

### Requirement: Singletons are App-scoped, not process-scoped

Two distinct `App` instances in the same process, each registering `singleton(T, ...)`, SHALL produce two distinct cached instances of `T`. The cache lives on the `App`, not on `T` and not in any process-global storage. This holds for both sync and async factory shapes; per-type locks for async coalescing live on the `Container`, not in process-global state.

#### Scenario: Two Apps, two singleton instances (sync)

- **GIVEN** `app_a = App("a").singleton(AppState, factory_a)` and `app_b = App("b").singleton(AppState, factory_b)`
- **WHEN** both Apps resolve `AppState`
- **THEN** the instance bound to `app_a`'s dispatch is distinct from the instance bound to `app_b`'s dispatch

#### Scenario: Two Apps, two singleton instances (async)

- **GIVEN** `app_a.singleton(SqliteResource, build_sqlite_async)` and `app_b.singleton(SqliteResource, build_sqlite_async)` registered with the same async factory function
- **WHEN** both Apps trigger async resolution of `SqliteResource`
- **THEN** the factory is awaited once per App
- **AND** each App caches its own distinct instance

### Requirement: Introspection surface

The `App` class SHALL expose `has_singleton(type_) -> bool` and `singletons() -> dict[type, Any]`. `has_singleton` SHALL return `True` once a singleton has been registered (before or after first resolve), regardless of whether the factory is sync or async. `singletons()` SHALL return a snapshot dict mapping registered types to their cached instances (or to a documented sentinel value for not-yet-resolved entries, which applies equally to async-factory singletons that have not yet been awaited).

#### Scenario: has_singleton before resolution (sync factory)

- **GIVEN** `app.singleton(AppState, factory)` registered with a sync factory but not yet resolved
- **WHEN** test code calls `app.has_singleton(AppState)`
- **THEN** the call returns `True`

#### Scenario: has_singleton before resolution (async factory)

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` registered with an async factory but not yet awaited
- **WHEN** test code calls `app.has_singleton(SqliteResource)`
- **THEN** the call returns `True`
- **AND** `app.singletons()[SqliteResource]` is the documented unresolved sentinel

### Requirement: Async-factory singletons coalesce concurrent first-resolution

When two or more coroutines concurrently request first-resolution of the same async-factory singleton, the container SHALL ensure the factory coroutine is awaited exactly once and all waiters receive the same resolved instance. The container SHALL use a per-type `asyncio.Lock` for this coalescing, created lazily on first async resolution of each type, so that concurrent first-touches of *different* async singletons do not serialize against each other.

#### Scenario: Two concurrent first-resolution awaiters share one factory call

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` not yet resolved
- **WHEN** two coroutines concurrently trigger async resolution of `SqliteResource`
- **THEN** `build_sqlite_async` is awaited exactly once
- **AND** both coroutines observe the same resolved instance

#### Scenario: Different async singletons resolve in parallel

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` and `app.singleton(BrowserPool, build_browser_async)`, neither resolved
- **WHEN** two coroutines concurrently trigger resolution of `SqliteResource` and `BrowserPool` respectively
- **THEN** both factories are awaited concurrently
- **AND** neither resolution blocks the other on a shared lock

#### Scenario: Async factory failure leaves the singleton resolvable on retry

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` where `build_sqlite_async` raises on first call
- **WHEN** the first async resolution propagates the exception
- **AND** a later async resolution is attempted after the failure condition is corrected
- **THEN** the factory is awaited again
- **AND** on success the resolved instance is cached for all subsequent resolves

### Requirement: Sync `resolve` of an unresolved async singleton raises a precise error

`container.resolve(T)` is synchronous. When `T` is registered with an async factory and has not yet been resolved (no cached instance), `container.resolve(T)` SHALL raise an error whose message names `T`, identifies the factory as async, and directs the caller to the framework's async resolve path (or to a startup warm-up via `@on_startup`). The container SHALL NOT attempt to run the event loop, schedule a task, or otherwise bridge sync-to-async transparently.

#### Scenario: Sync resolve before async first-touch raises

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` where `build_sqlite_async` has not been awaited
- **WHEN** sync code calls `container.resolve(SqliteResource)`
- **THEN** the call raises with a message naming `SqliteResource`, identifying the factory as async, and pointing the user at the async resolve path or `@on_startup` warm-up

#### Scenario: Sync resolve after async first-touch returns cached instance

- **GIVEN** an async-factory singleton already resolved via the async path
- **WHEN** sync code calls `container.resolve(T)`
- **THEN** the cached instance is returned without raising

### Requirement: `App.singleton` accepts `teardown=` for framework-managed shutdown

`App.singleton(type_, factory, *, teardown=None)` SHALL accept an optional `teardown` keyword argument. When provided, `teardown` is a callable taking one positional argument (the resolved singleton instance). It MAY be sync (`def`) or async (`async def`); async teardowns are awaited automatically. The framework SHALL invoke registered teardowns on App lifespan exit, regardless of whether the App also has a user-supplied `lifespan=` callable or Router-contributed lifespans.

#### Scenario: Basic teardown fires on lifespan exit

- **GIVEN** `app.singleton(Resource, build, teardown=lambda r: r.close())`
- **WHEN** the App's `lifespan_cm()` is entered and exited
- **THEN** `Resource.close()` is called exactly once after the lifespan exits

#### Scenario: Async teardown is awaited

- **GIVEN** `app.singleton(R, build, teardown=lambda r: r.aclose())` where `r.aclose()` returns a coroutine
- **WHEN** the App's lifespan exits
- **THEN** the coroutine is awaited to completion before `lifespan_cm()` returns

### Requirement: Teardown order is topological (dependents before dependencies)

When multiple singletons have registered teardowns AND their factories have parameter-graph dependencies on each other, the framework SHALL invoke teardowns in reverse-topological order: any singleton `T'` that another singleton `T` depends on (via `T`'s factory parameters) is torn down **after** `T`. Reverse-of-registration is NOT the contract; the topological derivation from the resolved DI graph is.

#### Scenario: BrowserPool depending on SqliteResource tears down first

- **GIVEN** `app.singleton(SqliteResource, build_sql, teardown=close_sql)` registered first, then `app.singleton(BrowserPool, build_pool, teardown=close_pool)` where `build_pool` declares a `SqliteResource` parameter
- **WHEN** the App's lifespan exits
- **THEN** `close_pool` is invoked before `close_sql`

### Requirement: Teardown failures are error-isolated

A teardown that raises `Exception` SHALL NOT prevent sibling teardowns from running. The framework SHALL catch the exception, record it on `App.teardown_failures` as `(type, exc)`, emit an `error`-level Python log line with the exception class, message, and singleton type name, and continue invoking the remaining teardowns in order. The framework SHALL NOT re-raise teardown exceptions from `lifespan_cm()`.

#### Scenario: One teardown raises; others still run; failure recorded

- **GIVEN** three singletons `A`, `B`, `C` each with a teardown; `B`'s teardown raises `RuntimeError("boom")`
- **WHEN** the App's lifespan exits
- **THEN** `A`'s and `C`'s teardowns both run (regardless of order between them and B)
- **AND** `app.teardown_failures` contains exactly one tuple `(B, RuntimeError("boom"))`
- **AND** an `error`-level log line was emitted naming `B` and the exception

### Requirement: Teardown without lifespan still fires

If an App has registered teardowns but no user-supplied `lifespan=` and no Router-contributed lifespan, the App's `lifespan_cm()` SHALL still return an async context manager that runs the teardowns on exit. `App.has_lifespan()` SHALL return True in this case.

#### Scenario: App with only teardowns has a lifespan

- **GIVEN** `app.singleton(R, build, teardown=close)` and no other lifespan registrations
- **WHEN** `app.has_lifespan()` is called
- **THEN** the call returns True
- **AND** `async with app.lifespan_cm():` enters and exits cleanly, running `close` on exit

### Requirement: Cycle in the singleton factory-parameter graph is handled deterministically

If the registered-singletons-with-teardowns subgraph contains a cycle (which the container's resolution-cycle detection should prevent in practice), `teardown_order()` SHALL break the cycle by emitting the lowest-`id` type and continuing, AND emit a `WARN`-level log line identifying the cycle and the break point.

#### Scenario: Cycle break is deterministic

- **GIVEN** a synthetic registration where two singletons mutually reference each other as factory parameters (constructed by direct provider manipulation in a test)
- **WHEN** `teardown_order()` is invoked
- **THEN** the call returns both types in a deterministic order (lowest-`id` first)
- **AND** a `WARN` log line is emitted identifying the cycle members and the break point

