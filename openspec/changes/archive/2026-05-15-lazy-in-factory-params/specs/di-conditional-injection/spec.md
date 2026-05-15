# di-conditional-injection Specification Delta

## MODIFIED Requirements

### Requirement: `Lazy[T]` is a type alias for deferred resolution

The framework SHALL expose `a2kit.Lazy` as a generic type alias
equivalent to `Callable[[], Awaitable[T]]`. Both **tool** and
**factory** parameters annotated `Lazy[T]` (or the unaliased
`Callable[[], Awaitable[T]]` form) SHALL be recognized by the
framework's parameter-resolution paths as deferred-resolution
requests for type `T`. The framework SHALL inject a closure that,
when awaited, resolves `T` in the resolving container's scope and
returns the resolved instance. The closure SHALL be a regular
awaitable callable; consumers MAY call it zero, one, or many
times.

This requirement applies uniformly across:

- **Tool dispatch** — `Container.resolve_params` (already
  implemented).
- **Factory construction** — `Container._construct_kwargs` (this
  change closes the spec-vs-implementation drift).

#### Scenario: Lazy[T] alias is importable

- **WHEN** a consumer writes `from a2kit import Lazy`
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

## ADDED Requirements

### Requirement: SINGLETON factories may not declare Lazy[per-call-type] parameters

The framework SHALL reject — at `async with app:` time via the
scope-graph validator — any SINGLETON-scope factory that declares
a parameter annotated `Lazy[T]` where `T` is registered with
`per_call=True`.

Rationale: `Container._make_lazy_closure` captures `self`
(the container the factory is being resolved on). SINGLETON
factories resolve on the root container, so the closure captures
root. Awaiting the closure later calls `root.get(per_call_T)`,
which routes into `_build_scoped` on root and populates
`root._scoped_cache`. The "per-call" semantics are silently
broken: the per-call type gets pinned to a single instance on
root for the app's lifetime, never refreshed across dispatches.

The error message SHALL name the offending factory, the parameter,
the per-call type, and the migration paths:

1. Move the inner type to app-scope (`per_call=False`).
2. Make the outer factory per-call (`per_call=True` on the
   aggregate), so the closure captures a per-call child whose
   parent-chain resolution honors the per-call scope.

This is a mirror of the existing scope-graph guard for direct
per-call dependencies of SINGLETON factories; it extends the
guard to deferred (`Lazy[T]`) dependencies, which today would
miswire silently.

#### Scenario: SINGLETON factory + Lazy[per-call-T] rejected at app entry

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)`
- **AND** `app.provide(AppState, make_state)` where `make_state` declares `tx: Lazy[Transaction]`
- **WHEN** the consumer enters `async with app:`
- **THEN** `TypeError` is raised
- **AND** the message names `AppState`, the parameter name (`tx`), the type `Lazy[Transaction]`, and both migration paths

#### Scenario: SINGLETON factory + Lazy[app-scope-T] accepted

- **GIVEN** `app.provide(BrowserPool, bp_factory)` (default app-scope)
- **AND** `app.provide(AppState, make_state)` where `make_state` declares `browser: Lazy[BrowserPool]`
- **WHEN** the consumer enters `async with app:`
- **THEN** no `TypeError` is raised
- **AND** subsequent dispatches resolve `AppState` and `Lazy[BrowserPool]` correctly per the existing scope semantics

#### Scenario: per-call factory + Lazy[per-call-T] accepted

- **GIVEN** `app.provide(Outer, outer_factory, per_call=True)` where `outer_factory` declares `inner: Lazy[Inner]`
- **AND** `app.provide(Inner, inner_factory, per_call=True)`
- **WHEN** the consumer enters `async with app:` and a tool depending on `Outer` is dispatched twice
- **THEN** no `TypeError` is raised at app entry
- **AND** each dispatch sees a fresh `Outer` instance
- **AND** awaiting the captured `inner` closure resolves `Inner` correctly through the per-call child container, with a fresh `Inner` per dispatch
