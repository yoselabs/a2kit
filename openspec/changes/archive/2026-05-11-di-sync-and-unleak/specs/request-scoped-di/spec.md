## MODIFIED Requirements

### Requirement: App provides typed factories via `App.provide(T, factory=None)`

The `App` class SHALL expose `provide(type_: type[T], factory: Callable[..., T] | None = None) -> Self` that registers a typed factory in a request-scoped DI container. When `factory` is omitted, the class `type_` itself SHALL be used as the factory and the container SHALL introspect `type_.__init__` to resolve constructor parameters. Calling `provide` with the same type twice SHALL replace the earlier factory (last-write-wins). `provide` constructs a fresh instance per dispatch; for App-scoped caching use `App.singleton(...)` instead. **Factories MUST be synchronous** (`def`, not `async def`); async factories raise `ValueError` at registration time.

#### Scenario: Class-as-factory shorthand
- **WHEN** an app is built with `app.provide(TrackerStore)` and `TrackerStore.__init__` is `def __init__(self, cfg: TrackerConfig)`
- **THEN** the type `TrackerStore` is resolvable from the container by calling `TrackerStore(cfg=<resolved TrackerConfig>)`

#### Scenario: Explicit factory
- **WHEN** an app is built with `app.provide(SearchIndex, lambda store: SearchIndex.warm(store))`
- **THEN** the type `SearchIndex` is resolvable; the container resolves `store` via the chain and calls the lambda

#### Scenario: Async factory rejected at registration

- **WHEN** `app.provide(Foo, async_factory)` is called with `async_factory` being an `async def`
- **THEN** `ValueError` is raised at registration naming the factory and pointing the user at the lazy-init resource pattern

#### Scenario: Primitive constructor param without default raises at registration
- **WHEN** `app.provide(BadStore)` is called and `BadStore.__init__` requires a non-default `int` parameter that no provider can supply
- **THEN** registration raises `ValueError` naming the unresolvable parameter

### Requirement: Container chains providers by parameter annotation

The container SHALL resolve a requested type by reading the registered factory's parameter annotations and recursively resolving each. A factory parameter annotated with a registered type SHALL be filled from the container. The container's public API SHALL NOT special-case any parameter name. Wire-input transformation (e.g. resolving a `connection: str` to a typed `ConnectionConfig`) happens via the dispatch hook seam, not inside the container.

#### Scenario: Two-link chain resolution
- **GIVEN** providers registered for `ConnectionConfig` (constructed from a `connection: str` substituted by the connections dispatch hook before container runs) and `TrackerStore` (taking `cfg: ConnectionConfig`)
- **WHEN** a tool method declares `store: TrackerStore` and is called with wire `connection="foo"`
- **THEN** the connections dispatch hook awaits the store load and substitutes a `ConnectionConfig` instance into wire kwargs
- **AND** the container synchronously resolves `TrackerStore` via its factory called with the already-resolved config
- **AND** the tool method receives `store` bound to the resolved instance

#### Scenario: Missing intermediate provider raises
- **GIVEN** a tool declares `store: TrackerStore` but no provider for `ConnectionConfig` is registered, while `TrackerStore`'s factory takes `cfg: ConnectionConfig`
- **WHEN** the tool is dispatched
- **THEN** the container raises `UnresolvableType(ConnectionConfig, chain=[TrackerStore])`

#### Scenario: Container API contains no feature names

- **WHEN** the source of `a2kit.packages.di.container` is grepped for the literal `"connection"`, `"tenant"`, `"tracker"`, or any other feature name
- **THEN** no occurrences are found

### Requirement: Synchronous resolve, no `connection` kwarg

The container SHALL expose `resolve(type_: type[T]) -> T` as a synchronous method. The legacy async `resolve` and `resolve_sync` are removed. `SyncResolveUnavailable` is removed. The `connection` keyword argument on resolve is removed.

#### Scenario: resolve is sync

- **GIVEN** a container with registered providers
- **WHEN** test code calls `container.resolve(AppState)`
- **THEN** the call returns synchronously; no `await` is required

#### Scenario: connection kwarg is gone

- **WHEN** test code calls `container.resolve(AppState, connection="foo")`
- **THEN** a `TypeError: unexpected keyword argument 'connection'` is raised

### Requirement: Per-call result caching

The container SHALL cache resolved instances within the lifetime of a single tool dispatch and SHALL NOT share instances across dispatches, except for types registered via `App.singleton(...)`, whose cached instance is shared across all dispatches on the App.

#### Scenario: Same type resolved twice in one call
- **GIVEN** a tool method declares both `store: TrackerStore` and `audit: AuditLog` where `AuditLog`'s factory also depends on `TrackerStore`
- **WHEN** the tool is dispatched
- **THEN** the `TrackerStore` instance bound to `store` and the one passed to the `AuditLog` factory are the same object

#### Scenario: Singleton instance shared across calls

- **GIVEN** `app.singleton(AppState, factory)` registered
- **WHEN** the same tool is dispatched twice
- **THEN** both dispatches receive the same `AppState` object

## REMOVED Requirements

### Requirement: Async factory registration

**Reason:** Async-in-DI added complexity (lock coalescing, sync/async chain analysis, two resolution paths) that paid for itself in zero real use cases once the connection-load case moved to the dispatch hook and async resource initialization moved to the lazy-init resource pattern. Singleton and provider factories are now sync-only.

**Migration:** Async resource initialization moves out of factories into resource classes that self-initialize on first use under an internal lock. See "Resource pattern" appendix.

### Requirement: Connection-config provider auto-installed by Connections plugin

**Reason:** The auto-install path registered a sync wrapper around an async store load, requiring the container to await factory results. With container sync-only, the equivalent now happens at the dispatch hook seam: `Connections.install(app)` installs an async hook that awaits the store load and substitutes the typed config into wire kwargs before the container resolves anything.

**Migration:** No consumer-facing API change; the substitution still happens, it just happens one layer up.
