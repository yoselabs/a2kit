# app-singletons — lifespan-over-lifecycle-hooks delta

## ADDED Requirements

### Requirement: `App.warm_async_singletons()` resolves every registered async singleton

The `a2kit.App` class SHALL expose `async def warm_async_singletons() -> None`
that iterates over registered singletons whose factory is async and
awaits each through the container, populating the cache. The
method SHALL be idempotent: calling it twice has the same effect
as calling it once. It SHALL respect the per-type coalescing lock
already required by this capability, so concurrent callers do not
double-resolve.

The canonical call site is the App's lifespan body before
`yield`. Calling it from elsewhere is permitted; calling it before
the lifespan is entered is permitted (the cache is App-scoped, not
lifespan-scoped).

#### Scenario: warm_async_singletons resolves every async-factory entry

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` and `app.singleton(BrowserPool, build_browser_async)`, both registered with async factories and neither resolved
- **WHEN** `await app.warm_async_singletons()` is awaited
- **THEN** both factories were awaited (the order MAY interleave; both factories MAY run concurrently); the cache has resolved instances for both types

#### Scenario: warm_async_singletons is idempotent

- **GIVEN** the call from the previous scenario already ran
- **WHEN** `await app.warm_async_singletons()` is awaited a second time
- **THEN** neither factory is re-awaited and the call returns without error

#### Scenario: Lifespan body warms async singletons before yield

- **GIVEN** an App with one async-factory singleton and a lifespan body that calls `await app.warm_async_singletons()` before `yield`
- **WHEN** the lifecycle enters
- **THEN** the async-factory singleton is resolved before any tool dispatch is permitted

## MODIFIED Requirements

### Requirement: Sync `resolve` of an unresolved async singleton raises a precise error

`container.resolve(T)` is synchronous; when `T` is registered with an async factory and has not yet been resolved (no cached instance), `container.resolve(T)` SHALL raise an error whose message names `T`, identifies the factory as async, and directs the caller to either the framework's async resolve path or a startup warm-up via `await app.warm_async_singletons()` called from the App's lifespan body, and the error message SHALL NOT reference the removed `@on_startup` decorator; the container SHALL NOT attempt to run the event loop, schedule a task, or otherwise bridge sync-to-async transparently.

#### Scenario: Sync resolve before async first-touch raises with lifespan-warmup hint

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` where `build_sqlite_async` has not been awaited
- **WHEN** sync code calls `container.resolve(SqliteResource)`
- **THEN** the call raises with a message that (a) names `SqliteResource`, (b) identifies the factory as async, and (c) directs the caller to call `await app.warm_async_singletons()` from the App's lifespan body (or use an async resolve path directly)

#### Scenario: Error message does not reference @on_startup

- **WHEN** the error message text from the previous scenario is inspected
- **THEN** the substring `on_startup` does not appear anywhere in the message
