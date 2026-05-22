## MODIFIED Requirements

### Requirement: `Lazy[T]` is a type alias for deferred resolution

The framework SHALL expose `a2kit.packages.di.Lazy` as a generic type alias equivalent to `Callable[[], Awaitable[T]]`.
Both **tool** and **factory** parameters annotated `Lazy[T]` (or the unaliased `Callable[[], Awaitable[T]]` form) SHALL be recognized by the framework's parameter-resolution paths as deferred-resolution requests for type `T`. The framework SHALL inject a closure that, when awaited, resolves `T` in the resolving container's scope and returns the resolved instance. The closure SHALL be a regular awaitable callable; consumers MAY call it zero, one, or many times.

This requirement applies uniformly across:

- **Tool dispatch** — `Container.resolve_params` (already
  implemented).
- **Factory construction** — `Container._construct_kwargs` (this
  change closes the spec-vs-implementation drift).

#### Scenario: Lazy[T] alias is importable

- **WHEN** a consumer writes `from a2kit.packages.di import Lazy`
- **THEN** the import succeeds
- **AND** `Lazy[BrowserPool]` is equivalent to `Callable[[], Awaitable[BrowserPool]]` for type-checker purposes

#### Scenario: Tool body declaring Lazy[T] receives a callable

- **GIVEN** `app.provide(BrowserPool)` is registered and a tool declares `browser: Lazy[BrowserPool]`
- **WHEN** the tool is dispatched
- **THEN** the value bound to `browser` is callable
- **AND** awaiting `browser()` returns a `BrowserPool` instance
- **AND** the value bound to `browser` is not itself a `BrowserPool` instance

#### Scenario: Lazy[T] closure never invoked — resource never resolved

- **GIVEN** `app.provide(BrowserPool)` is registered (app-scope, lazy) and a tool declares `browser: Lazy[BrowserPool]` but the tool body never calls `browser()`
- **WHEN** the tool is dispatched
- **THEN** `BrowserPool`'s factory or `__aenter__` is not invoked
- **AND** no cleanup is registered for the resource

#### Scenario: Factory parameter declaring Lazy[T] receives a callable

- **GIVEN** `app.provide(BrowserPool)` is registered (app-scope, lazy) and an aggregate `AppState` is provided via a factory `def make_state(browser: Lazy[BrowserPool]) -> AppState`
- **WHEN** `AppState` is first resolved (on a tool dispatch that injects `state: AppState`)
- **THEN** the value bound to the factory's `browser` parameter is callable
- **AND** the factory stores the thunk on `AppState` (e.g. `AppState.browser_pool = browser`)
- **AND** `BrowserPool.__aenter__` is not yet invoked

#### Scenario: Aggregate carrying Lazy[T] field — thunk awaited from tool body

- **GIVEN** the above setup with `AppState.browser_pool: Lazy[BrowserPool]`
- **AND** a tool that does `state: AppState`, body calls `bp = await state.browser_pool()`
- **WHEN** the tool dispatches
- **THEN** `BrowserPool.__aenter__` runs exactly once (on this first await across the app's lifetime)
- **AND** the returned instance is cached as an app-scope singleton
- **AND** a subsequent tool dispatch awaiting `state.browser_pool()` returns the same instance without re-entering

#### Scenario: Factory-injected Lazy[T] never awaited — resource never resolved

- **GIVEN** `AppState` factory takes `browser: Lazy[BrowserPool]` and stores it on the aggregate, but no tool body ever awaits the thunk
- **WHEN** the app runs through any number of dispatches
- **THEN** `BrowserPool`'s factory or `__aenter__` is never invoked
- **AND** no cleanup is recorded for `BrowserPool`
