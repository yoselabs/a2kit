## MODIFIED Requirements

### Requirement: App SHALL implement the async context manager protocol

The `a2kit.App` class SHALL implement `__aenter__` and `__aexit__`. `async with app:` SHALL be the canonical entry point for the App's lifecycle. App construction (`a2kit.App(...)` plus subsequent `add_router(...)` / `singleton(...)` calls) SHALL be pure: no async work, no singleton `__aenter__`, no router `__aenter__`. The first `__aenter__` invocation on the App SHALL be the only event that triggers framework-owned resource entry. Singletons SHALL be entered in topological order over the DI graph restricted to the registered set, with registration order as the tiebreaker between unrelated singletons. Unwind SHALL be LIFO over the realised entry order.

#### Scenario: Construction is pure

- **GIVEN** `app = a2kit.App("api")` followed by `app.singleton(DB)` and `app.add_router(Github())`
- **WHEN** the constructor and registration calls return
- **THEN** no `__aenter__` method on any singleton or Router has been invoked

#### Scenario: `async with app` enters singletons

- **GIVEN** an App with singletons `A`, `B` registered (no DI relationship)
- **WHEN** `async with app:` is entered
- **THEN** both `A.__aenter__` and `B.__aenter__` have been invoked exactly once before the body runs

#### Scenario: Dependent enters after dependency regardless of registration order

- **GIVEN** singletons `A` and `B(A)` where `B`'s factory declares `A` as a parameter, registered in the order `B`-then-`A`
- **WHEN** `async with app:` is entered
- **THEN** `A.__aenter__` ran before `B.__aenter__`

#### Scenario: Unrelated singletons preserve registration order

- **GIVEN** singletons `X`, `Y`, `Z` registered in that order with no DI relationship between them
- **WHEN** `async with app:` is entered
- **THEN** entry order is `X` then `Y` then `Z`

#### Scenario: `async with app` exit unwinds in LIFO order

- **GIVEN** an App with singletons `A`, `B` entered during `__aenter__`
- **WHEN** the `async with` block exits normally
- **THEN** `B.__aexit__` ran before `A.__aexit__`
