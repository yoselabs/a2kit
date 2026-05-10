## ADDED Requirements

### Requirement: Container exposes `resolve_sync(T)` for sync-only chains

The container SHALL expose `resolve_sync(type_: type[T], *, connection: str | None = None) -> T`. The method SHALL traverse the provider graph reachable from `type_`; if every factory in the chain is non-async, it SHALL resolve them synchronously and return the resulting instance. If any factory in the reachable chain is async, the method SHALL raise `SyncResolveUnavailable(type_, async_link=<offending type>)` whose message names the first async factory encountered. Singleton-cached values are returned directly without re-traversal.

#### Scenario: Sync chain resolves synchronously

- **GIVEN** providers for `Settings` (sync), `Store` (sync, takes `Settings`)
- **WHEN** `container.resolve_sync(Store)` is called
- **THEN** the call returns a `Store` instance without entering an event loop

#### Scenario: Async link raises with named offender

- **GIVEN** providers for `Settings` (sync) and `AsyncBackend` (async, takes `Settings`)
- **WHEN** `container.resolve_sync(AsyncBackend)` is called
- **THEN** `SyncResolveUnavailable` is raised with `async_link=AsyncBackend`

#### Scenario: Singleton cached value resolved synchronously regardless of original factory

- **GIVEN** `app.singleton(AppState, async_factory)` and `AppState` has already been resolved once via the async path
- **WHEN** `container.resolve_sync(AppState)` is called
- **THEN** the cached instance is returned without re-invoking the factory

## MODIFIED Requirements

### Requirement: App provides typed factories via `App.provide(T, factory=None)`

The `App` class SHALL expose `provide(type_: type[T], factory: Callable[..., T] | None = None) -> Self` that registers a typed factory in a request-scoped DI container. When `factory` is omitted, the class `type_` itself SHALL be used as the factory and the container SHALL introspect `type_.__init__` to resolve constructor parameters. Calling `provide` with the same type twice SHALL replace the earlier factory (last-write-wins). `provide` constructs a fresh instance per dispatch; for App-scoped caching use `App.singleton(...)` instead.

#### Scenario: Class-as-factory shorthand
- **WHEN** an app is built with `app.provide(TrackerStore)` and `TrackerStore.__init__` is `def __init__(self, cfg: TrackerConfig)`
- **THEN** the type `TrackerStore` is resolvable from the container by calling `TrackerStore(cfg=<resolved TrackerConfig>)`

#### Scenario: Explicit factory
- **WHEN** an app is built with `app.provide(SearchIndex, lambda store: SearchIndex.warm(store))`
- **THEN** the type `SearchIndex` is resolvable; the container resolves `store` via the chain and calls the lambda

#### Scenario: Async factory registration
- **WHEN** a registered factory is `async`
- **THEN** the container resolves it with `await` during dispatch and the resolved instance is bound to the tool kwarg

#### Scenario: Primitive constructor param without default raises at registration
- **WHEN** `app.provide(BadStore)` is called and `BadStore.__init__` requires a non-default `int` parameter that no provider can supply
- **THEN** registration raises `ValueError` naming the unresolvable parameter

#### Scenario: provide and singleton on same type — last-write-wins, but with override warning

- **WHEN** `app.provide(AppState, factory_a)` is called and then `app.singleton(AppState, factory_b)` is called
- **THEN** the singleton registration replaces the per-dispatch one
- **AND** subsequent resolves use the cached singleton

### Requirement: Container chains providers by parameter annotation

The container SHALL resolve a requested type by reading the registered factory's parameter annotations and recursively resolving each. A factory parameter annotated with a registered type SHALL be filled from the container; a factory parameter named `connection` of type `str` SHALL be filled from the wire `connection` arg of the active tool call when present, or from `None` when the call site supplied no connection. The async `resolve` method SHALL accept `connection` as a keyword argument with default `None`; the synchronous `resolve_sync` method SHALL adopt the same default.

#### Scenario: Two-link chain resolution
- **GIVEN** providers registered for `ConnectionConfig` (taking `connection: str`) and `TrackerStore` (taking `cfg: ConnectionConfig`)
- **WHEN** a tool method declares `store: TrackerStore` and is called with wire `connection="foo"`
- **THEN** the container resolves `ConnectionConfig` via its factory called with `connection="foo"`
- **AND** the container resolves `TrackerStore` via its factory called with the resolved config
- **AND** the tool method receives `store` bound to the resolved instance

#### Scenario: Missing intermediate provider raises
- **GIVEN** a tool declares `store: TrackerStore` but no provider for `ConnectionConfig` is registered, while `TrackerStore`'s factory takes `cfg: ConnectionConfig`
- **WHEN** the tool is dispatched
- **THEN** the container raises `UnresolvableType(ConnectionConfig, chain=[TrackerStore])`

#### Scenario: Connection-less resolve omits the kwarg

- **GIVEN** an app with no connection plugin installed
- **WHEN** test code calls `await app.container().resolve(AppState)` with no `connection` argument
- **THEN** the call succeeds and resolves `AppState` exactly as it does in tool dispatch
- **AND** no `TypeError: missing required keyword 'connection'` is raised

### Requirement: Per-call result caching

The container SHALL cache resolved instances within the lifetime of a single tool dispatch and SHALL NOT share instances across dispatches, except for types registered via `App.singleton(...)`, whose cached instance is shared across all dispatches on the App.

#### Scenario: Same type resolved twice in one call
- **GIVEN** a tool method declares both `store: TrackerStore` and `audit: AuditLog` where `AuditLog`'s factory also depends on `TrackerStore`
- **WHEN** the tool is dispatched
- **THEN** the `TrackerStore` instance bound to `store` and the one passed to the `AuditLog` factory are the same object

#### Scenario: Fresh instances across calls
- **WHEN** the same tool is dispatched twice with the same `connection` value
- **THEN** the second call constructs new instances; no instance is shared with the first call

#### Scenario: Singleton instance shared across calls

- **GIVEN** `app.singleton(AppState, factory)` registered
- **WHEN** the same tool is dispatched twice
- **THEN** both dispatches receive the same `AppState` object
