## MODIFIED Requirements

### Requirement: App exposes `singleton(T, factory=None)` registration

The `a2kit.App` class SHALL expose `singleton(type_: type[T], factory: Callable[..., T] | None = None)` that registers a typed factory whose result is cached on the `App` instance and shared across all dispatches that resolve `type_`. When `factory` is omitted, the call SHALL return a decorator that accepts the factory function and completes the registration. **Factories MUST be synchronous** (`def`, not `async def`); async factories raise `ValueError` at registration time.

#### Scenario: Method form

- **WHEN** `app.singleton(AppState, lambda: AppState(...))` is called with a sync factory
- **THEN** `AppState` is resolvable from the container
- **AND** the factory is invoked at most once per `App` instance

#### Scenario: Decorator form

- **WHEN** a function `def build_state(s: Settings) -> AppState: ...` is decorated with `@app.singleton(AppState)`
- **THEN** the function is registered as the cached factory for `AppState` and returned unchanged

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

Two distinct `App` instances in the same process, each registering `singleton(T, ...)`, SHALL produce two distinct cached instances of `T`. The cache lives on the `App`, not on `T` and not in any process-global storage.

#### Scenario: Two Apps, two singleton instances

- **GIVEN** `app_a = App("a").singleton(AppState, factory_a)` and `app_b = App("b").singleton(AppState, factory_b)`
- **WHEN** both Apps resolve `AppState`
- **THEN** the instance bound to `app_a`'s dispatch is distinct from the instance bound to `app_b`'s dispatch

### Requirement: Introspection surface

The `App` class SHALL expose `has_singleton(type_) -> bool` and `singletons() -> dict[type, Any]`. `has_singleton` SHALL return `True` once a singleton has been registered (before or after first resolve). `singletons()` SHALL return a snapshot dict mapping registered types to their cached instances (or to a documented sentinel value for not-yet-resolved entries).

#### Scenario: has_singleton before resolution

- **GIVEN** `app.singleton(AppState, factory)` registered but not yet resolved
- **WHEN** test code calls `app.has_singleton(AppState)`
- **THEN** the call returns `True`

## REMOVED Requirements

### Requirement: Async factories supported with concurrency-safe initialization

**Reason:** Async resource initialization moves out of DI factories into resource classes (the lazy-init pattern). The lock-coalescing concurrency-safe init logic moves into the resource class itself. The DI container becomes pure typed-map + chain-resolve, sync end-to-end.

**Migration:** Convert async factories into sync factories that construct resource wrapper classes; move the async open logic into the resource class behind an `_ensure` accessor with its own internal lock.

### Requirement: Singleton factories MUST NOT depend on `connection`

**Reason:** The rule was a guard against an architectural mistake (connection-scoped state in an App-scoped cache). With `connection` no longer a magic name in the container or core, the rule's specific shape no longer applies. The replacement rule "singleton factories must be sync" transitively rejects connection-dependent factories, since connection loading is async and would force `async def`.

**Migration:** None required. Factories that previously needed `connection` already had to be moved to `provide`; that path is unchanged.
