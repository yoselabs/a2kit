# in-process-test-client Specification Delta

## ADDED Requirements

### Requirement: Async DI resolution test seam

The system SHALL provide `a2kit.testing.resolve(app, type_)` — an
async helper that resolves a registered type through the App's
container using the same path as production tool dispatch. The
function SHALL run the full DI resolution chain, building the type
via its registered factory (chaining constructor-parameter
resolution), entering `__aenter__` for resources, and recording
cleanup on the appropriate scope's stack (root for SINGLETON,
child for SCOPED).

`resolve` SHALL be the async sibling of `peek`. Where `peek` reads
already-cached singletons from `Container._singletons`, `resolve`
triggers the full resolution chain — including building the type
on first call. Subsequent calls SHALL return cached instances per
the registered scope's semantics.

Callers SHALL invoke `resolve` inside an entered app context
(`async with a2kit.testing.client(app):` or `async with app:`) so
the cleanup stack is alive to receive recorded `__aexit__`
callbacks. Calling outside an entered app is undefined and matches
today's `await app.container().get(T)` semantics — resources may
end up half-entered without a scope to exit them.

`a2kit.testing.resolve` SHALL be importable as
`from a2kit.testing import resolve` and appear in
`a2kit.testing.__all__`.

#### Scenario: resolve runs the DI chain on first call

- **GIVEN** `app.provide(_Inner)` where `_Inner.__init__` increments a class-level counter
- **WHEN** the test does `async with app: instance = await a2kit.testing.resolve(app, _Inner)`
- **THEN** `_Inner.instances_created == 1`
- **AND** `instance` is an `_Inner`

#### Scenario: resolve enters resources via __aenter__

- **GIVEN** `_Inner` implements `__aenter__` / `__aexit__` with counters and is registered as a singleton
- **WHEN** the test resolves `_Inner` once inside `async with app:`
- **THEN** `_Inner.entered == 1` after the resolve returns
- **AND** `_Inner.exited == 0` while the lifespan is still in flight
- **AND** `_Inner.exited == 1` after the lifespan exits

#### Scenario: resolve returns cached singleton on second call

- **GIVEN** `_Inner` registered as a singleton (default `per_call=False`)
- **WHEN** the test calls `resolve(app, _Inner)` twice in the same lifespan
- **THEN** both calls return the same instance by identity
- **AND** `_Inner.__aenter__` was invoked exactly once

#### Scenario: resolve walks the dependency chain

- **GIVEN** `app.provide(_Inner)` and `app.provide(_Outer)` where `_Outer`'s factory takes an `_Inner` parameter
- **WHEN** the test calls `await a2kit.testing.resolve(app, _Outer)` inside `async with app:`
- **THEN** the returned `_Outer` is fully constructed with the resolved `_Inner` injected into its factory
- **AND** subsequent `resolve(app, _Inner)` returns the same `_Inner` instance the outer factory received
