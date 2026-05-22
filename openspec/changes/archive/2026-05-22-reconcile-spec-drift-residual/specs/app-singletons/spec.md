## MODIFIED Requirements

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
