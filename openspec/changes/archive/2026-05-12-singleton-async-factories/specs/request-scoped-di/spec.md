## MODIFIED Requirements

### Requirement: App provides typed factories via `App.provide(T, factory=None)`

The `App` class SHALL expose `provide(type_: type[T], factory: Callable[..., T] | None = None) -> Self` that registers a typed factory in a request-scoped DI container. When `factory` is omitted, the class `type_` itself SHALL be used as the factory and the container SHALL introspect `type_.__init__` to resolve constructor parameters. Calling `provide` with the same type twice SHALL replace the earlier factory (last-write-wins). `provide` constructs a fresh instance per dispatch; for App-scoped caching use `App.singleton(...)` instead. **`provide` factories MUST be synchronous** (`def`, not `async def`); async factories on `provide` raise `ValueError` at registration time. This restriction applies only to `provide`; `singleton` accepts both sync and async factories (see the `app-singletons` capability).

#### Scenario: Class-as-factory shorthand
- **WHEN** an app is built with `app.provide(TrackerStore)` and `TrackerStore.__init__` is `def __init__(self, cfg: TrackerConfig)`
- **THEN** the type `TrackerStore` is resolvable from the container by calling `TrackerStore(cfg=<resolved TrackerConfig>)`

#### Scenario: Explicit factory
- **WHEN** an app is built with `app.provide(SearchIndex, lambda store: SearchIndex.warm(store))`
- **THEN** the type `SearchIndex` is resolvable; the container resolves `store` via the chain and calls the lambda

#### Scenario: Async factory rejected on `provide`

- **WHEN** `app.provide(Foo, async_factory)` is called with `async_factory` being an `async def`
- **THEN** `ValueError` is raised at registration naming the factory and directing the user to `app.singleton(...)` for App-scoped async-initialized resources

#### Scenario: Primitive constructor param without default raises at registration
- **WHEN** `app.provide(BadStore)` is called and `BadStore.__init__` requires a non-default `int` parameter that no provider can supply
- **THEN** registration raises `ValueError` naming the unresolvable parameter

#### Scenario: provide and singleton on same type — last-write-wins, but with override warning

- **WHEN** `app.provide(AppState, factory_a)` is called and then `app.singleton(AppState, factory_b)` is called
- **THEN** the singleton registration replaces the per-dispatch one
- **AND** subsequent resolves use the cached singleton
- **AND** `factory_b` MAY be sync or async per the `app-singletons` capability
