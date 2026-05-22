# di-conditional-injection Specification

## Purpose
TBD - created by archiving change di-scoped-lifecycle. Update Purpose after archive.
## Requirements
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

### Requirement: `Lazy[T]` honors registered scope

The closure injected for a `Lazy[T]` parameter SHALL resolve `T` through the same container path as direct injection would. App-scope (`per_call=False`) resources resolved via `Lazy[T]` SHALL share the App-scope cache: the first invocation across all calls enters the resource, and subsequent invocations across all calls return the cached instance. Per-call (`per_call=True`) resources resolved via `Lazy[T]` SHALL share the per-call cache: the first invocation within a given dispatch enters the resource, subsequent invocations within the same dispatch return the same instance, and a fresh instance is created in a subsequent dispatch.

#### Scenario: Lazy[T] of app-scope returns cached instance across calls

- **GIVEN** `app.provide(BrowserPool)` (app-scope, lazy)
- **WHEN** tool A dispatches and calls `await browser()` (where `browser: Lazy[BrowserPool]`), and later tool B dispatches and calls `await browser()`
- **THEN** both calls return the same `BrowserPool` instance
- **AND** `BrowserPool.__aenter__` was invoked exactly once

#### Scenario: Lazy[T] called twice within one tool returns same instance

- **GIVEN** `app.provide(BrowserPool)` (app-scope) and a tool that does `bp1 = await browser(); bp2 = await browser()`
- **WHEN** the tool is dispatched
- **THEN** `bp1 is bp2`
- **AND** `BrowserPool.__aenter__` was invoked exactly once across the two calls

#### Scenario: Lazy[T] of per-call type returns same instance within call, fresh across calls

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool declaring `tx: Lazy[Transaction]` that calls `await tx()` twice
- **WHEN** the tool is dispatched twice
- **THEN** within each dispatch the two `await tx()` invocations return the same `Transaction` instance
- **AND** across the two dispatches the returned `Transaction` instances are not the same object
- **AND** `tx_factory` was invoked exactly twice (once per dispatch)

### Requirement: `Lazy[T]` participates in cleanup like direct injection

A resource resolved through a `Lazy[T]` closure SHALL be registered on the same scope's cleanup stack as if it had been resolved through a directly-injected parameter. App-scope resources resolved lazily SHALL be cleaned up at App `__aexit__`. Per-call resources resolved lazily SHALL be cleaned up at the per-call scope's exit (tool return or raise).

#### Scenario: Lazy-resolved app-scope resource cleaned up at App exit

- **GIVEN** `app.provide(BrowserPool)` (app-scope) where `BrowserPool` implements `__aenter__`/`__aexit__`, and a tool that resolves it via `await browser()` where `browser: Lazy[BrowserPool]`
- **WHEN** the tool dispatches once, then the App exits via `async with app:` block close
- **THEN** `BrowserPool.__aexit__` is invoked exactly once during App close

#### Scenario: Lazy-resolved per-call resource cleaned up at call exit

- **GIVEN** `app.provide(Transaction, tx_factory, per_call=True)` and a tool that resolves it via `await tx()` where `tx: Lazy[Transaction]`
- **WHEN** the tool is dispatched and returns normally
- **THEN** the per-call scope's cleanup stack runs the transaction's `__aexit__` / generator-yield `finally` before the dispatch result is returned to the caller

### Requirement: Unannotated lazy parameters raise at registration

When a tool or factory declares a parameter whose annotation cannot be resolved (e.g., `Callable[[], Awaitable[T]]` where `T` has no registered provider and is not auto-resolvable as a `BaseSettings` subclass), the framework SHALL raise `TypeError` at App `__aenter__` time (graph validation), naming the tool and the parameter and the unresolvable inner type.

#### Scenario: Lazy of unregistered type fails at graph validation

- **GIVEN** a tool declares `dep: Lazy[UnregisteredType]` and no provider for `UnregisteredType` is registered
- **WHEN** `async with app:` is entered
- **THEN** `TypeError` is raised
- **AND** the message names the tool name, the parameter `"dep"`, and the type `"UnregisteredType"`

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

