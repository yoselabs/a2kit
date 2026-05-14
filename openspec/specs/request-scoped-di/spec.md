# request-scoped-di Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: App provides typed factories via `App.provide(T, factory=None)`

**Reshaped: `provide` is unified across app-scope and per-call scope; sync-only restriction removed; per-dispatch fresh instances are now opt-in via `per_call=True` not the default.** The `App` class SHALL expose `provide(type_: type[T], factory: Callable[..., T] | None = None, *, per_call: bool = False) -> Self` that registers a typed factory. When `factory` is omitted, the class `type_` itself SHALL be used as the factory and the container SHALL introspect `type_.__init__` to resolve constructor parameters. Calling `provide` with the same type twice SHALL replace the earlier factory (last-write-wins) — this is the canonical mechanism for test-time overrides via composition-root re-registration.

When `per_call=False` (default), the resolved instance SHALL be cached on the App-scope root container (see `app-singletons` for app-scope semantics). When `per_call=True`, the resolved instance SHALL be cached within the per-call child container opened by the dispatcher for a single tool invocation (see `di-per-call-scope`).

**The sync-only restriction on `provide` SHALL be removed.** Async factories are accepted on both `per_call=False` and `per_call=True` registrations. Async factories on `per_call=True` SHALL be awaited each dispatch the resource is resolved; async factories on `per_call=False` SHALL be awaited once across the App's lifetime per the lock-coalesce contract.

#### Scenario: Class-as-factory shorthand (app-scope default)

- **WHEN** an app is built with `app.provide(TrackerStore)` and `TrackerStore.__init__` is `def __init__(self, cfg: TrackerConfig)`
- **THEN** the type `TrackerStore` is resolvable from the container by calling `TrackerStore(cfg=<resolved TrackerConfig>)`
- **AND** the resolved instance is cached at app-scope (default)

#### Scenario: Explicit factory (per-call)

- **WHEN** an app is built with `app.provide(SearchIndex, lambda store: SearchIndex.warm(store), per_call=True)`
- **THEN** the type `SearchIndex` is resolvable per dispatch; the container resolves `store` via the chain and calls the lambda fresh for each dispatch

#### Scenario: Async factory accepted on `provide` (both scopes)

- **WHEN** `app.provide(Foo, async_factory)` is called with `async_factory` being an `async def` returning `Foo`
- **THEN** the registration succeeds without raising
- **AND** the framework awaits `async_factory` on first resolution and caches at app-scope

- **WHEN** `app.provide(Bar, async_factory, per_call=True)` is called
- **THEN** the registration succeeds
- **AND** the framework awaits `async_factory` once per dispatch within the per-call scope

#### Scenario: Primitive constructor param without default raises at registration

- **WHEN** `app.provide(BadStore)` is called and `BadStore.__init__` requires a non-default `int` parameter that no provider can supply
- **THEN** registration raises `ValueError` naming the unresolvable parameter

#### Scenario: Re-registration is last-write-wins (test override pattern)

- **WHEN** `app.provide(Database, real_db_factory)` is called and then `app.provide(Database, fake_db_factory)` is called (e.g., in `build_test_app()`)
- **THEN** subsequent resolutions of `Database` use `fake_db_factory`
- **AND** no `TypeError` or warning is raised — this is the supported test override mechanism

### Requirement: Container chains providers by parameter annotation

The container SHALL resolve a requested type by reading the registered factory's parameter annotations and recursively resolving each. A factory parameter annotated with a registered type SHALL be filled from the container. The container's public API SHALL NOT special-case any parameter name. Wire-input transformation (e.g. resolving a `connection: str` to a typed `ConnectionConfig`) happens via the dispatch hook seam, not inside the container.

**Reshaped: resolution may cross scope boundaries when a per-call factory depends on app-scope types.** When a per-call factory's parameter resolves to an app-scope type, the resolver SHALL pull from the App-scope root container; the resolved app-scope instance SHALL NOT be duplicated into the per-call child. The reverse (an app-scope factory depending on a per-call type) SHALL be rejected at App `__aenter__` with `TypeError`.

#### Scenario: Two-link chain resolution

- **GIVEN** providers registered for `ConnectionConfig` (constructed from a `connection: str` substituted by the connections dispatch hook before container runs) and `TrackerStore` (taking `cfg: ConnectionConfig`)
- **WHEN** a tool method declares `store: TrackerStore` and is called with wire `connection="foo"`
- **THEN** the connections dispatch hook awaits the store load and substitutes a `ConnectionConfig` instance into wire kwargs
- **AND** the container resolves `TrackerStore` via its factory called with the already-resolved config
- **AND** the tool method receives `store` bound to the resolved instance

#### Scenario: Missing intermediate provider raises

- **GIVEN** a tool declares `store: TrackerStore` but no provider for `ConnectionConfig` is registered, while `TrackerStore`'s factory takes `cfg: ConnectionConfig`
- **WHEN** the tool is dispatched
- **THEN** the container raises `UnresolvableType(ConnectionConfig, chain=[TrackerStore])`

#### Scenario: Per-call factory may depend on app-scope type

- **GIVEN** `app.provide(ConnectionPool)` (app-scope) and `app.provide(Transaction, tx_factory, per_call=True)` where `tx_factory(pool: ConnectionPool)`
- **WHEN** a tool is dispatched and resolves `Transaction`
- **THEN** the per-call child container resolves `pool` from the App-scope root (entering `ConnectionPool` lazily on first dispatch)
- **AND** the per-call `Transaction` is constructed with the app-scope pool
- **AND** `ConnectionPool` is not duplicated into the per-call child

#### Scenario: App-scope cannot depend on per-call

- **GIVEN** `app.provide(Foo, foo_factory)` where `foo_factory(bar: Bar)` and `app.provide(Bar, bar_factory, per_call=True)`
- **WHEN** `async with app:` is entered (graph validation runs)
- **THEN** `TypeError` is raised
- **AND** the message names `"Foo"`, `"Bar"`, and the phrase `"app-scope depends on per-call"`

#### Scenario: Container API contains no feature names

- **WHEN** the source of `a2kit.packages.di` is grepped for `"connection"`, `"tracker"`, or other feature-suggestive strings
- **THEN** no matches are found in code or attribute names (docstrings that explicitly enumerate "this container has no feature awareness" as the contract are the only allowed mentions)

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

