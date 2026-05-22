## ADDED Requirements

### Requirement: App exposes `provide(...)` registration

The `a2kit.App` class SHALL expose `provide(...)` as the unified registration API for typed factories. App-scope caching is the default behavior (`per_call=False`, kwarg omitted). The method SHALL accept three call shapes: (a) `provide(SomeClass)` where the class itself is the factory and the registered type is the class; (b) `provide(factory)` where the factory's return-type annotation provides the registered type (sync `def`, `async def`, or annotated-return generators are accepted; unannotated lambdas with non-zero parameters remain forbidden); (c) `provide(BaseClass, factory)` for explicit override where the factory returns a subtype but the registration should be under the base. The call SHALL return `self` for chaining.

When the one-arg form receives a callable with no return type annotation, the framework SHALL raise `TypeError` at registration naming the call site and proposing both fixes (annotate the factory or pass the type explicitly). The `TypeError` message SHALL name `app.provide` as the surface, not `app.singleton`.

The method name `singleton(...)` does not exist on `App`. Accessing `app.singleton` SHALL raise the standard Python `AttributeError` for a missing attribute — the framework does not host a renamed-method interceptor that produces a hinted `TypeError` (the `App.__getattr__` interceptor that previously did so was removed).

#### Scenario: Class-as-factory form (zero-arg ctor)

- **WHEN** `app.provide(AppState)` is called with no second argument
- **THEN** `AppState` itself is used as the factory at first resolve
- **AND** the registered type is `AppState`
- **AND** the call returns `self`

#### Scenario: Factory-only form with return annotation

- **GIVEN** `async def build_state() -> AppState: ...`
- **WHEN** `app.provide(build_state)` is called
- **THEN** the registered type is `AppState` (read from the return annotation)
- **AND** the call returns `self`

#### Scenario: Explicit base-type override

- **GIVEN** `class SubState(AppState): ...` and `def make() -> SubState: ...`
- **WHEN** `app.provide(AppState, make)` is called
- **THEN** the registered type is `AppState` (not `SubState`)

#### Scenario: Unannotated factory raises naming app.provide

- **WHEN** `app.provide(lambda: AppState(...))` is called (no annotation on the lambda return)
- **THEN** `TypeError` is raised at registration whose message names both `"return annotation"` and `"app.provide(T, factory)"` as the explicit-override fix

#### Scenario: app.singleton is a missing attribute

- **WHEN** `app.singleton` is accessed on an `App` instance
- **THEN** Python raises `AttributeError` because `App` has no `singleton` attribute

### Requirement: App-scope registrations resolve via the request-scoped container

An app-scope registration SHALL be reachable via `Resolver.get(T)` (async). The first call to `get(T)` after registration SHALL invoke the factory exactly once, await the result if the factory is async, run `__aenter__` if the resolved instance implements the async context manager protocol, record the cleanup callable on the App-scope cleanup stack, and cache the resolved instance. Subsequent `get(T)` calls on any scope (including child scopes opened by the dispatcher) SHALL return the cached instance without re-entering the factory.

Concurrent first-touch resolutions of the same app-scope type SHALL coalesce on a per-type `asyncio.Lock` — the factory and `__aenter__` SHALL be invoked at most once across the racing callers.

#### Scenario: App-scope resolved twice returns the same instance

- **GIVEN** `app.provide(AppState, factory)` where `factory` returns a fresh instance each time it is called
- **WHEN** the container resolves `AppState` twice (across two dispatches or two `get` calls)
- **THEN** both resolves return the same object
- **AND** `factory` was invoked exactly once
- **AND** `AppState.__aenter__` was invoked exactly once if the class implements the async context manager protocol

#### Scenario: Concurrent first-touches coalesce

- **GIVEN** an async-factory app-scope registration for `SqliteResource`
- **WHEN** ten concurrent tasks each trigger first-resolution of `SqliteResource`
- **THEN** the factory is awaited exactly once
- **AND** `SqliteResource.__aenter__` runs exactly once
- **AND** all ten tasks share the same resolved instance

### Requirement: App-scope registrations are App-scoped, not process-scoped

Two distinct `App` instances in the same process, each registering `provide(T, ...)` (with `per_call=False`, the default), SHALL produce two distinct cached instances of `T`. The cache lives on the `App`'s container, not on `T` and not in any process-global storage. This holds for both sync and async factory shapes.

#### Scenario: Two Apps, two app-scope instances (sync)

- **GIVEN** `app_a = App("a").provide(AppState, factory_a)` and `app_b = App("b").provide(AppState, factory_b)`
- **WHEN** both Apps resolve `AppState`
- **THEN** the instance bound to `app_a`'s dispatch is distinct from the instance bound to `app_b`'s dispatch

#### Scenario: Two Apps, two app-scope instances (async)

- **GIVEN** `app_a.provide(SqliteResource, build_sqlite_async)` and `app_b.provide(SqliteResource, build_sqlite_async)` registered with the same async factory function
- **WHEN** both Apps trigger async resolution of `SqliteResource`
- **THEN** the factory is awaited once per App
- **AND** each App caches its own distinct instance

## MODIFIED Requirements

### Requirement: Introspection surface

The `App` class SHALL expose `providers() -> dict[type, Any]` returning a snapshot dict mapping registered types to their cached instances (for app-scope) or to a documented sentinel for not-yet-resolved or per-call entries. The method names `has_singleton(...)` and `singletons()` do not exist on `App`; accessing either SHALL raise the standard Python `AttributeError` for a missing attribute. The framework does not host a renamed-method interceptor for these names.

#### Scenario: providers returns a snapshot dict

- **GIVEN** `app.provide(AppState, factory)` registered but not yet resolved
- **WHEN** test code calls `app.providers()`
- **THEN** the call returns a dict whose `AppState` entry is the documented not-yet-resolved sentinel

#### Scenario: has_singleton and singletons are missing attributes

- **WHEN** `app.has_singleton` or `app.singletons` is accessed on an `App` instance
- **THEN** Python raises `AttributeError` because `App` has no such attribute

## REMOVED Requirements

### Requirement: App exposes `singleton(T, factory=None)` registration

**Reason**: `singleton(...)` is not a method on `App`; it was renamed to `provide(..., per_call=False)`. The requirement specified that calling `app.singleton(...)` raise a hinted `TypeError`, but the `App.__getattr__` interceptor that delivered that hint was removed when the app runtime was internalized. Accessing `app.singleton` now raises a plain `AttributeError`. Specifying "a missing attribute raises `AttributeError`" specifies Python, not a2kit. The live `provide` surface is covered by the ADDED "App exposes `provide(...)` registration" requirement.

**Migration**: Replace `app.singleton(T, factory)` with `app.provide(T, factory)` and `app.singleton(T, factory, per_call_equivalent...)` semantics with the `per_call=` keyword on `provide`. There is no hinted error to catch — the dead name is simply absent.

### Requirement: Singletons resolve via the request-scoped container

**Reason**: Renamed to "App-scope registrations resolve via the request-scoped container" (see the ADDED requirement). The "singleton" vocabulary was retired when `singleton(...)` became `provide(..., per_call=False)`; the resolution contract itself is unchanged.

**Migration**: None — terminology only. The resolution behavior is specified identically under the new requirement name.

### Requirement: Singletons are App-scoped, not process-scoped

**Reason**: Renamed to "App-scope registrations are App-scoped, not process-scoped" (see the ADDED requirement). The "singleton" vocabulary was retired when `singleton(...)` became `provide(..., per_call=False)`; the scoping contract itself is unchanged.

**Migration**: None — terminology only. The scoping behavior is specified identically under the new requirement name.

### Requirement: Teardown failures are error-isolated

**Reason**: This requirement asserts `App.teardown_failures` as a `(type, exc)` accumulator and a `lifespan_cm()` method. Neither exists on `App`. Teardown failure isolation is owned by the `di-scope-cleanup-stack` capability (LIFO unwind, per-resource exception isolation, WARN-level logging via `a2kit.di.cleanup`); the App-level `teardown_failures` attribute and `lifespan_cm()` surface were superseded by that contract.

**Migration**: For teardown-failure behavior, consult the `di-scope-cleanup-stack` capability and the `app-lifecycle` "Singleton or router `__aexit__` failure SHALL log and continue unwinding" requirement. There is no `App.teardown_failures` to read; cleanup failures are logged at WARN, not accumulated on the App.
