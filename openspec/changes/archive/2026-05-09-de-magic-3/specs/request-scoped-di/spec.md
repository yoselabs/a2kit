## ADDED Requirements

### Requirement: App provides typed factories via `App.provide(T, factory=None)`

The `App` class SHALL expose `provide(type_: type[T], factory: Callable[..., T] | None = None) -> Self` that registers a typed factory in a request-scoped DI container. When `factory` is omitted, the class `type_` itself SHALL be used as the factory and the container SHALL introspect `type_.__init__` to resolve constructor parameters. Calling `provide` with the same type twice SHALL replace the earlier factory (last-write-wins).

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

### Requirement: Container chains providers by parameter annotation

The container SHALL resolve a requested type by reading the registered factory's parameter annotations and recursively resolving each. A factory parameter annotated with a registered type SHALL be filled from the container; a factory parameter named `connection` of type `str` SHALL be filled from the wire `connection` arg of the active tool call.

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

### Requirement: Per-call result caching

The container SHALL cache resolved instances within the lifetime of a single tool dispatch and SHALL NOT share instances across dispatches.

#### Scenario: Same type resolved twice in one call
- **GIVEN** a tool method declares both `store: TrackerStore` and `audit: AuditLog` where `AuditLog`'s factory also depends on `TrackerStore`
- **WHEN** the tool is dispatched
- **THEN** the `TrackerStore` instance bound to `store` and the one passed to the `AuditLog` factory are the same object

#### Scenario: Fresh instances across calls
- **WHEN** the same tool is dispatched twice with the same `connection` value
- **THEN** the second call constructs new instances; no instance is shared with the first call

### Requirement: Connection-config provider auto-installed by Connections plugin

When an `App` is configured with `add_cli(connections_cli(ConfigT))` (or any other Connections plugin entry point that registers a `Connections[ConfigT]` typed registry), the framework SHALL automatically install a provider for `ConfigT` whose factory takes `connection: str` and resolves it via the registered `Connections[ConfigT]`. App authors SHALL NOT be required to call `app.provide(ConfigT, ...)` manually.

#### Scenario: Auto-installed config provider
- **GIVEN** an app with `app.add_cli(connections_cli(TrackerConfig))` and no manual `provide(TrackerConfig, ...)`
- **WHEN** a tool method declares `cfg: TrackerConfig` or any chained provider depends on it
- **THEN** dispatch resolves `cfg` via the auto-installed factory
- **AND** the wire schema includes `connection: str`

#### Scenario: Manual override of auto-installed provider
- **GIVEN** the connections plugin auto-installed a `TrackerConfig` provider, then app calls `app.provide(TrackerConfig, custom_factory)`
- **WHEN** dispatch resolves `TrackerConfig`
- **THEN** the custom factory is used (last-write-wins)

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

The container SHALL treat `ToolContext` and `App` as always-provided: when a tool method declares a kwarg of either type, the framework dispatch hook fills the value without requiring an `App.provide()` registration.

#### Scenario: ToolContext is filled implicitly
- **GIVEN** a tool method `async def import_tasks(self, *, ctx: a2kit.ToolContext, store: TrackerStore, ...) -> ...`
- **WHEN** the tool is dispatched
- **THEN** `ctx` is bound by the framework and `store` is bound by the container

### Requirement: Lint enforces provider availability

Lint rule `A2K-DI-PROVIDER` SHALL fail when any tool method declares an injectable kwarg type that is not registered in the App's container and is not on the always-provided allowlist (`ToolContext`, `App`).

#### Scenario: Missing provider fails lint
- **GIVEN** a router declares a tool with `store: TrackerStore` but the test harness builds an `App` without `provide(TrackerStore, ...)`
- **WHEN** `make lint` runs
- **THEN** `A2K-DI-PROVIDER` reports `TrackerStore` as missing in the app graph
