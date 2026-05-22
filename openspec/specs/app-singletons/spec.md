# app-singletons Specification

## Purpose
TBD - created by archiving change app-lifecycle-and-di-ergonomics. Update Purpose after archive.
## Requirements
### Requirement: Introspection surface

The `App` class SHALL expose `providers() -> dict[type, Any]` returning a snapshot dict mapping registered types to their cached instances (for app-scope) or to a documented sentinel for not-yet-resolved or per-call entries. `providers()` is the sole DI-introspection method on the App surface.

#### Scenario: providers returns a snapshot dict

- **GIVEN** `app.provide(AppState, factory)` registered but not yet resolved
- **WHEN** test code calls `app.providers()`
- **THEN** the call returns a dict whose `AppState` entry is the documented not-yet-resolved sentinel

#### Scenario: providers reflects resolved instances

- **GIVEN** `app.provide(AppState, factory)` that has been resolved by a dispatch
- **WHEN** test code calls `app.providers()`
- **THEN** the `AppState` entry holds the cached app-scope instance

### Requirement: App-scope is the default scope of `provide`

The `App.provide(...)` method SHALL accept a keyword-only `per_call: bool = False` argument. When `per_call=False` (the default, equivalent to omitting the kwarg), the registered type SHALL be cached on the App's root container for the App's lifetime. When `per_call=True`, the registration SHALL participate in the per-call scope contract (see `di-per-call-scope`).

#### Scenario: per_call omitted defaults to app-scope

- **GIVEN** `app.provide(AppState, factory)` with no `per_call` kwarg
- **WHEN** two dispatches each resolve `AppState`
- **THEN** both dispatches receive the same cached instance
- **AND** the factory was invoked exactly once across the two dispatches

#### Scenario: per_call=False explicit reads identically

- **GIVEN** `app.provide(AppState, factory, per_call=False)` (explicit)
- **WHEN** two dispatches each resolve `AppState`
- **THEN** behavior is identical to omitting `per_call` (same cached instance, factory invoked once)

### Requirement: App-scope resolution is lazy by default

App-scope registrations SHALL NOT be entered at `AppRuntime.__aenter__`. The first dispatch that resolves a given app-scope type SHALL trigger its factory invocation and `__aenter__` call. An app-scope type that no dispatch ever resolves SHALL NOT have its factory invoked, regardless of registration order or graph reachability.

#### Scenario: Unused app-scope resource never entered

- **GIVEN** `app.provide(BrowserPool)` and `app.provide(SqliteResource)` both registered, where `BrowserPool` implements `__aenter__`/`__aexit__`
- **WHEN** the App is entered, a tool that resolves only `SqliteResource` is dispatched, and the App exits
- **THEN** `BrowserPool.__aenter__` was never invoked
- **AND** `BrowserPool.__aexit__` was never invoked
- **AND** the App close completes normally

#### Scenario: First dispatch warms the resource; subsequent dispatches reuse

- **GIVEN** `app.provide(BrowserPool)` (lazy by default)
- **WHEN** the first dispatch needs `BrowserPool` and resolves it, then a second dispatch needs `BrowserPool` and resolves it
- **THEN** `BrowserPool.__aenter__` ran exactly once (during the first dispatch's resolution)
- **AND** both dispatches received the same instance

### Requirement: pydantic-settings subclasses auto-resolve without explicit registration

The container SHALL auto-resolve a requested type `T` when `T` is a subclass of `pydantic_settings.BaseSettings` and no explicit provider for `T` is registered. Auto-resolution SHALL invoke `T()` (zero-arg construction; pydantic-settings reads env on construction) and cache the result at app-scope. This rule SHALL be the only special-case auto-resolution rule applied by the container; no other zero-arg-constructible class is auto-resolved.

The container SHALL NOT import `pydantic_settings` directly. Subclass detection SHALL use duck-typing (e.g., `hasattr(cls, "model_config")` plus inheritance hierarchy walk) so the container remains usable without pydantic installed.

#### Scenario: Settings class resolved without registration

- **GIVEN** `class SmtpSettings(BaseSettings): host: str; model_config = SettingsConfigDict(env_prefix="SMTP_")` and `SMTP_HOST=localhost` in the environment
- **WHEN** a tool declares `settings: SmtpSettings` and is dispatched
- **THEN** the framework constructs `SmtpSettings()` (which reads env)
- **AND** the tool receives a `SmtpSettings(host="localhost")` instance

#### Scenario: Non-BaseSettings type with no registration raises

- **GIVEN** a class `Foo` (not a `BaseSettings` subclass) with no registration
- **WHEN** a tool declares `foo: Foo` and is dispatched
- **THEN** `UnresolvableType` is raised naming `Foo` and the tool

#### Scenario: BaseSettings cached across dispatches

- **GIVEN** `SmtpSettings` auto-resolved on first dispatch
- **WHEN** a second dispatch also needs `SmtpSettings`
- **THEN** both dispatches receive the same `SmtpSettings` instance
- **AND** the constructor was invoked exactly once

### Requirement: App exposes `provide(...)` registration

The `a2kit.App` class SHALL expose `provide(...)` as the unified registration API for typed factories. App-scope caching is the default behavior (`per_call=False`, kwarg omitted). The method SHALL accept three call shapes: (a) `provide(SomeClass)` where the class itself is the factory and the registered type is the class; (b) `provide(factory)` where the factory's return-type annotation provides the registered type (sync `def`, `async def`, or annotated-return generators are accepted; unannotated lambdas with non-zero parameters remain forbidden); (c) `provide(BaseClass, factory)` for explicit override where the factory returns a subtype but the registration should be under the base. The call SHALL return `self` for chaining.

When the one-arg form receives a callable with no return type annotation, the framework SHALL raise `TypeError` at registration naming the call site and proposing both fixes (annotate the factory or pass the type explicitly). The `TypeError` message SHALL name `app.provide` as the surface.

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

