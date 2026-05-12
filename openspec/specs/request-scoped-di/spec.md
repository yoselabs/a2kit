# request-scoped-di Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
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

### Requirement: Connection-rooted resolution boundary

Exactly the auto-installed config provider SHALL be permitted to take a parameter named `connection` of type `str`. No other provider — manual or auto — SHALL receive raw `connection: str`. This invariant SHALL be enforced by lint rule `A2K-DI-CHAIN`.

#### Scenario: Lint rejects non-config provider taking connection:str
- **WHEN** lint scans an `app.provide(TrackerStore, lambda connection: ...)` registration whose annotated parameter type is `str`
- **THEN** `A2K-DI-CHAIN` reports a violation pointing at the offending provider

### Requirement: Wire-schema partition strips injectable kwargs

For each tool method, the framework SHALL partition kwargs into wire kwargs (primitive / pydantic / stdlib container types) and injectable kwargs (types matching a registered provider). Synthesized MCP tool input schema and Click CLI command options SHALL include only wire kwargs. The framework SHALL also auto-include `connection: str` in the wire schema whenever any kwarg's resolution chain reaches the `ConnectionConfig` provider.

#### Scenario: Schema strips injected store
- **GIVEN** a tool method `async def get_task(self, *, store: TrackerStore, task_id: str) -> Task`
- **WHEN** the MCP tool schema is generated
- **THEN** the schema input properties include `task_id` and `connection` but NOT `store`

#### Scenario: Schema omits connection when no chain reaches it
- **GIVEN** a tool method `async def ping(self, *, message: str) -> str` with no DI dependencies
- **WHEN** the MCP tool schema is generated
- **THEN** the schema input properties include `message` only

### Requirement: Always-provided allowlist for framework types

The container SHALL treat `fastmcp.Context` (re-exported as `a2kit.ToolContext`) and `App` as always-provided: when a tool method declares a kwarg of either type, the framework dispatch hook fills the value without requiring an `App.provide()` registration. Because `a2kit.ToolContext is fastmcp.Context` evaluates to `True`, both annotation styles resolve to the same allowlisted entry.

#### Scenario: ToolContext is filled implicitly
- **GIVEN** a tool method `async def import_tasks(self, *, ctx: a2kit.ToolContext, store: TrackerStore, ...) -> ...`
- **WHEN** the tool is dispatched
- **THEN** `ctx` is bound by the framework (the live `fastmcp.Context` under `serve`, the CLI stub under CLI) and `store` is bound by the container

#### Scenario: fastmcp.Context annotation also allowlisted
- **GIVEN** a tool method `async def t(self, *, ctx: fastmcp.Context) -> dict`
- **WHEN** the tool is dispatched
- **THEN** `ctx` is bound by the framework without requiring an `App.provide(fastmcp.Context, ...)` call

### Requirement: Lint enforces provider availability

Lint rule `A2K-DI-PROVIDER` SHALL fail when any tool method declares an injectable kwarg type that is not registered in the App's container and is not on the always-provided allowlist (`fastmcp.Context` and `App`).

#### Scenario: Missing provider fails lint
- **GIVEN** a router declares a tool with `store: TrackerStore` but the test harness builds an `App` without `provide(TrackerStore, ...)`
- **WHEN** `make lint` runs
- **THEN** `A2K-DI-PROVIDER` reports `TrackerStore` as missing in the app graph

#### Scenario: ctx parameter does not require a provider
- **GIVEN** a tool method declaring only `ctx: a2kit.ToolContext` as an injectable
- **WHEN** `make lint` runs
- **THEN** `A2K-DI-PROVIDER` does not report `fastmcp.Context` as missing

