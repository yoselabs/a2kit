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

### Requirement: Per-call result caching

The container SHALL cache resolved instances within the lifetime of a single tool dispatch and SHALL NOT share instances across dispatches, except for types registered with app scope (`app.provide(T, ...)` with `per_call=False`, the default), whose cached instance is shared across all dispatches on the App.

#### Scenario: Same type resolved twice in one call

- **GIVEN** a tool method declares both `store: TrackerStore` and `audit: AuditLog` where `AuditLog`'s factory also depends on `TrackerStore`
- **WHEN** the tool is dispatched
- **THEN** the `TrackerStore` instance bound to `store` and the one passed to the `AuditLog` factory are the same object

#### Scenario: App-scope instance shared across calls

- **GIVEN** `app.provide(AppState, factory)` registered (default `per_call=False`)
- **WHEN** the same tool is dispatched twice
- **THEN** both dispatches receive the same `AppState` object

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

### Requirement: Production dispatch routes through `Container.call_scope`

Both production dispatch sites (`mcp/server.py::_wrap_with_dispatch_hook` and `cli/runtime.py::_invoke_tool_in_process`) SHALL invoke tools through `app._resolver.call_scope(fn, wire_kwargs, pre_hook=<hook>)`. The async-CM opens a per-call child container, optionally calls the wire-side `pre_hook`, runs `resolve_params(fn)` for DI (Lazy[T] aware), merges, yields kwargs for the wrapper to call `fn(**kw)`, and unwinds the child's cleanup stack on exit.

#### Scenario: per_call resource cleaned up at MCP call exit

- **GIVEN** a tool dispatched through `fastmcp.Client(transport=build_mcp_server(app))`
- **AND** `app.provide(Transaction, per_call=True)` registered
- **AND** the tool body resolves `tx: Transaction`
- **WHEN** the tool returns normally
- **THEN** the `Transaction.__aexit__` runs with `exc=None` exactly once
- **WHEN** the tool raises
- **THEN** the `Transaction.__aexit__` runs with the propagating
  exception exactly once
- **AND** the wire error envelope reflects the body exception (not the
  cleanup state)

#### Scenario: Lazy[T] never invoked under real MCP wire

- **GIVEN** a tool `async def f(b: Lazy[Browser])` dispatched via real
  MCP transport
- **WHEN** the body completes without awaiting `b()`
- **THEN** `Browser.__aenter__` never runs
- **AND** the child container's cleanup stack has no Browser entry to unwind

#### Scenario: per_call resource cleaned up at CLI call exit

- **GIVEN** a tool dispatched via `<app> <tool> --args ...` (CLI runtime)
- **AND** `app.provide(Transaction, per_call=True)` registered
- **WHEN** the CLI invocation completes
- **THEN** `Transaction.__aexit__` ran exactly once, AFTER the tool body

### Requirement: Hookless dispatch composes without `identity_dispatch_hook`

Apps that install no dispatch hook (no connections, no custom hook) SHALL still route through `Container.call_scope(fn, wire_kwargs)` with no `pre_hook` argument. The framework MUST NOT require a sentinel identity function for the no-hook path.

#### Scenario: No-hook tool path

- **GIVEN** an App with no `install_connections` and no `app._dispatch_hook` override
- **WHEN** a tool is dispatched
- **THEN** the wrapper opens `app._resolver.call_scope(fn, wire)` without `pre_hook`
- **AND** the tool body sees DI-resolved kwargs merged with wire kwargs

### Requirement: Container exposes the v0.36+ resolution surface

The `Container` class SHALL provide this resolution + registration surface as the only callable path for new code:

- `provide(type_, factory, *, scope=Scope.SINGLETON)`
- `has_provider(type_)`
- `providers_view()`
- async `get(type_)`
- async `resolve_params(fn)`
- async `call_scope(fn, wire_kwargs, *, pre_hook=None)` (async context manager)
- `child()`
- async `aclose()`
- async `__aenter__` / `__aexit__`

The legacy method names (`register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, `has_any_async_singletons`) are removed — they do not resolve to any attribute and accessing one raises `AttributeError`. The test-only `_override` / `_snapshot` / `_restore` seam does NOT exist — it was deleted. Test-time dependency swaps are done by composition-root re-registration (constructing a fresh `App` and calling `provide` with the fake), not by mutating a sealed container.

#### Scenario: new surface is callable

- **GIVEN** a fresh `Container` instance
- **WHEN** new-surface methods are called against a registered type
- **THEN** `provide`, `has_provider`, `providers_view`, `get`, `resolve_params`, `call_scope`, `child`, `aclose` complete without raising `TypeError`

#### Scenario: no test-override seam exists

- **WHEN** `packages/di/container.py` is inspected for `_override`, `_snapshot`, `_restore`
- **THEN** no such member is defined on `Container`

### Requirement: `Principal` is a SCOPED provider when present

The active `call_scope` SHALL carry the request's `Principal` as a SCOPED provider whenever a substrate produces one. Tool bodies and `authorize=` callables SHALL resolve `principal: Principal` by type annotation alone. The provider SHALL be written by the substrate adapter, not by author code. When no `Principal` is produced (unauthenticated path), the framework-installed placeholder provider SHALL raise `RuntimeError` if a body actually depends on `Principal`.

#### Scenario: Scope carries Principal when authenticated

- **GIVEN** an authenticated request producing `Principal(subject="u1", ...)`
- **WHEN** the dispatch wrapper enters `call_scope`
- **THEN** `scope.get(Principal).subject == "u1"`

### Requirement: Legacy DI method names are removed

The legacy DI method names SHALL be removed from `Container`: `register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, and `has_any_async_singletons`. The names SHALL NOT resolve to any attribute; accessing one raises the language-default `AttributeError` with no embedded migration hint and no alias. The replacements (`provide`, `get`, `has_provider`) are documented in the CHANGELOG.

#### Scenario: legacy `register` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.register`
- **THEN** `AttributeError` is raised

#### Scenario: legacy `resolve` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.resolve`
- **THEN** `AttributeError` is raised

#### Scenario: legacy `has` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.has`
- **THEN** `AttributeError` is raised

