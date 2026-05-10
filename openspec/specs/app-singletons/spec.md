# app-singletons Specification

## Purpose
TBD - created by archiving change app-lifecycle-and-di-ergonomics. Update Purpose after archive.
## Requirements
### Requirement: App exposes `singleton(T, factory=None)` registration

The `a2kit.App` class SHALL expose `singleton(type_: type[T], factory: Callable[..., T] | None = None)` that registers a typed factory whose result is cached on the `App` instance and shared across all dispatches that resolve `type_`. When `factory` is omitted, the call SHALL return a decorator that accepts the factory function and completes the registration. The method SHALL return the `App` instance for chaining (when called as a method) or the decorator (when used decorator-style).

#### Scenario: Method form

- **WHEN** `app.singleton(AppState, lambda: AppState(...))` is called
- **THEN** `AppState` is resolvable from the container
- **AND** the factory is invoked at most once per `App` instance

#### Scenario: Decorator form

- **WHEN** a function is decorated with `@app.singleton(AppState)`
- **THEN** the function is registered as the cached factory for `AppState` and returned unchanged

### Requirement: Singletons are App-scoped, not process-scoped

Two distinct `App` instances in the same process, each registering `singleton(T, ...)`, SHALL produce two distinct cached instances of `T`. The cache lives on the `App`, not on `T` and not in any process-global storage.

#### Scenario: Two Apps, two singleton instances

- **GIVEN** `app_a = App("a").singleton(AppState, factory_a)` and `app_b = App("b").singleton(AppState, factory_b)`
- **WHEN** both Apps resolve `AppState`
- **THEN** the instance bound to `app_a`'s dispatch is distinct from the instance bound to `app_b`'s dispatch
- **AND** `factory_a` ran only for `app_a` and `factory_b` ran only for `app_b`

### Requirement: Singletons resolve via the request-scoped container

A registered singleton SHALL be reachable via `container.resolve(T, ...)` and `container.resolve_sync(T)` exactly like a `provide`-registered type. The container SHALL receive the cached instance on every resolve after the first.

#### Scenario: Singleton resolved twice returns the same instance

- **GIVEN** `app.singleton(AppState, factory)` where `factory` returns a fresh instance each time it is called
- **WHEN** the container resolves `AppState` twice (across two dispatches or two `resolve` calls)
- **THEN** both resolves return the same object
- **AND** `factory` was invoked exactly once

#### Scenario: Singleton dependency chains

- **GIVEN** `app.singleton(AppState, lambda settings: AppState(settings))` and `app.provide(Settings, load_settings)`
- **WHEN** a tool method declares `state: AppState`
- **THEN** the container resolves `Settings` (per-dispatch), then resolves `AppState` once via `lambda settings: ...`
- **AND** subsequent dispatches reuse the cached `AppState` and do not re-call the factory

### Requirement: Async factories supported with concurrency-safe initialization

If the registered factory is an async function, the runtime SHALL invoke it under an `asyncio.Lock` on first resolve such that concurrent resolvers wait for the in-flight initialization and receive the same cached instance. Subsequent resolves after the cache is populated SHALL NOT acquire the lock.

#### Scenario: Concurrent first-resolve coalesces

- **GIVEN** `app.singleton(BrowserPool, async_factory)` where `async_factory` takes 100ms
- **WHEN** ten concurrent dispatches resolve `BrowserPool`
- **THEN** `async_factory` was awaited exactly once
- **AND** all ten dispatches received the same `BrowserPool` instance

### Requirement: Singleton factories MUST NOT depend on `connection`

At registration time, the runtime SHALL inspect the factory's parameters. If any parameter resolves to a connection-bound dependency (a parameter named `connection` of type `str`, or any registered type whose factory chain ultimately requires `connection`), `singleton(...)` SHALL raise `ValueError` naming the offending parameter. Connection-bound state belongs in `provide`, not `singleton`.

#### Scenario: Direct connection dependency rejected

- **WHEN** `app.singleton(PerConn, lambda connection: PerConn(connection))` is called
- **THEN** registration raises `ValueError` whose message names `connection` and points the user at `provide`

#### Scenario: Transitive connection dependency rejected

- **GIVEN** `app.provide(ConnConfig, lambda connection: ...)` already registered
- **WHEN** `app.singleton(Cached, lambda cfg: Cached(cfg))` is called and `cfg: ConnConfig`
- **THEN** registration raises `ValueError` referencing the transitive chain `Cached → ConnConfig → connection`

### Requirement: Introspection surface

The `App` class SHALL expose `has_singleton(type_) -> bool` and `singletons() -> dict[type, Any]`. `has_singleton` SHALL return `True` once a singleton has been registered (before or after first resolve). `singletons()` SHALL return a snapshot dict mapping registered types to their cached instances (or to a documented sentinel value for not-yet-resolved entries).

#### Scenario: has_singleton before resolution

- **WHEN** `app.singleton(AppState, factory)` has been called but no resolve has occurred
- **THEN** `app.has_singleton(AppState)` is `True`

#### Scenario: singletons() reflects cache state

- **WHEN** `AppState` has been resolved once
- **THEN** `app.singletons()[AppState]` is the cached instance
- **AND** types registered but not yet resolved are present in the dict with the documented unresolved sentinel

