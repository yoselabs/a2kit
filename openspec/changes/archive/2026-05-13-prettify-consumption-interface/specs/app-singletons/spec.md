## MODIFIED Requirements

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
