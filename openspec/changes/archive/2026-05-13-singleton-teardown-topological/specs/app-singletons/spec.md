# app-singletons — singleton-teardown-topological delta

## ADDED Requirements

### Requirement: `App.singleton` accepts `teardown=` for framework-managed shutdown

`App.singleton(type_, factory, *, teardown=None)` SHALL accept an optional `teardown` keyword argument. When provided, `teardown` is a callable taking one positional argument (the resolved singleton instance). It MAY be sync (`def`) or async (`async def`); async teardowns are awaited automatically. The framework SHALL invoke registered teardowns on App lifespan exit, regardless of whether the App also has a user-supplied `lifespan=` callable or Router-contributed lifespans.

#### Scenario: Basic teardown fires on lifespan exit

- **GIVEN** `app.singleton(Resource, build, teardown=lambda r: r.close())`
- **WHEN** the App's `lifespan_cm()` is entered and exited
- **THEN** `Resource.close()` is called exactly once after the lifespan exits

#### Scenario: Async teardown is awaited

- **GIVEN** `app.singleton(R, build, teardown=lambda r: r.aclose())` where `r.aclose()` returns a coroutine
- **WHEN** the App's lifespan exits
- **THEN** the coroutine is awaited to completion before `lifespan_cm()` returns

### Requirement: Teardown order is topological (dependents before dependencies)

When multiple singletons have registered teardowns AND their factories have parameter-graph dependencies on each other, the framework SHALL invoke teardowns in reverse-topological order: any singleton `T'` that another singleton `T` depends on (via `T`'s factory parameters) is torn down **after** `T`. Reverse-of-registration is NOT the contract; the topological derivation from the resolved DI graph is.

#### Scenario: BrowserPool depending on SqliteResource tears down first

- **GIVEN** `app.singleton(SqliteResource, build_sql, teardown=close_sql)` registered first, then `app.singleton(BrowserPool, build_pool, teardown=close_pool)` where `build_pool` declares a `SqliteResource` parameter
- **WHEN** the App's lifespan exits
- **THEN** `close_pool` is invoked before `close_sql`

### Requirement: Teardown failures are error-isolated

A teardown that raises `Exception` SHALL NOT prevent sibling teardowns from running. The framework SHALL catch the exception, record it on `App.teardown_failures` as `(type, exc)`, emit an `error`-level Python log line with the exception class, message, and singleton type name, and continue invoking the remaining teardowns in order. The framework SHALL NOT re-raise teardown exceptions from `lifespan_cm()`.

#### Scenario: One teardown raises; others still run; failure recorded

- **GIVEN** three singletons `A`, `B`, `C` each with a teardown; `B`'s teardown raises `RuntimeError("boom")`
- **WHEN** the App's lifespan exits
- **THEN** `A`'s and `C`'s teardowns both run (regardless of order between them and B)
- **AND** `app.teardown_failures` contains exactly one tuple `(B, RuntimeError("boom"))`
- **AND** an `error`-level log line was emitted naming `B` and the exception

### Requirement: Teardown without lifespan still fires

If an App has registered teardowns but no user-supplied `lifespan=` and no Router-contributed lifespan, the App's `lifespan_cm()` SHALL still return an async context manager that runs the teardowns on exit. `App.has_lifespan()` SHALL return True in this case.

#### Scenario: App with only teardowns has a lifespan

- **GIVEN** `app.singleton(R, build, teardown=close)` and no other lifespan registrations
- **WHEN** `app.has_lifespan()` is called
- **THEN** the call returns True
- **AND** `async with app.lifespan_cm():` enters and exits cleanly, running `close` on exit

### Requirement: Cycle in the singleton factory-parameter graph is handled deterministically

If the registered-singletons-with-teardowns subgraph contains a cycle (which the container's resolution-cycle detection should prevent in practice), `teardown_order()` SHALL break the cycle by emitting the lowest-`id` type and continuing, AND emit a `WARN`-level log line identifying the cycle and the break point.

#### Scenario: Cycle break is deterministic

- **GIVEN** a synthetic registration where two singletons mutually reference each other as factory parameters (constructed by direct provider manipulation in a test)
- **WHEN** `teardown_order()` is invoked
- **THEN** the call returns both types in a deterministic order (lowest-`id` first)
- **AND** a `WARN` log line is emitted identifying the cycle members and the break point
