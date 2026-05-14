# app-singletons — consolidate-lifecycle-on-async-cm-protocol delta

## MODIFIED Requirements

### Requirement: App exposes `singleton(T, factory=None)` registration

The `a2kit.App` class SHALL expose `singleton(...)` that registers a typed factory whose resolved instance is cached on the `App` and shared across all dispatches that resolve the type. The method SHALL accept three call shapes: (a) `singleton(SomeClass)` where the class itself is the factory and the registered type is the class; (b) `singleton(factory)` where the factory's return-type annotation provides the registered type (sync `def`, `async def`, or annotated lambda are accepted); (c) `singleton(BaseClass, factory)` for explicit override where the factory returns a subtype but the registration should be under the base. The call SHALL return `self` for chaining. When the one-arg form receives a callable with no return type annotation, the framework SHALL raise `TypeError` at registration naming the call site and proposing both fixes (annotate the factory or pass the type explicitly).

#### Scenario: Class-as-factory form (zero-arg ctor)

- **WHEN** `app.singleton(AppState)` is called with no second argument
- **THEN** `AppState` itself is used as the factory at resolve time
- **AND** the registered type is `AppState`
- **AND** the call returns `self`

#### Scenario: Factory-only form with return annotation

- **GIVEN** `async def build_state() -> AppState: ...`
- **WHEN** `app.singleton(build_state)` is called
- **THEN** the registered type is `AppState` (read from the return annotation)
- **AND** the call returns `self`

#### Scenario: Explicit base-type override

- **GIVEN** `class SubState(AppState): ...` and `def make() -> SubState: ...`
- **WHEN** `app.singleton(AppState, make)` is called
- **THEN** the registered type is `AppState` (not `SubState`)

#### Scenario: Unannotated factory raises with hint

- **WHEN** `app.singleton(lambda: AppState(...))` is called (no annotation on the lambda return)
- **THEN** `TypeError` is raised at registration whose message names both `"return annotation"` and `"app.singleton(T, factory)"` as the explicit-override fix

### Requirement: `App.singleton` accepts `teardown=` for framework-managed shutdown

`App.singleton(...)` SHALL NOT accept a `teardown=` keyword argument. Resource cleanup SHALL be carried by the resolved instance itself via Python's standard protocols. The framework SHALL probe the resolved instance for cleanup in the following order and SHALL wire whichever it finds into the App's `AsyncExitStack`:

1. `__aexit__` (with matching `__aenter__`): the instance is entered via `__aenter__` at App `__aenter__` time and exited via `__aexit__` at App `__aexit__` time.
2. `aclose()` (no `__aexit__`): `await instance.aclose()` is scheduled for App `__aexit__`.
3. `close()` (neither of the above): `instance.close()` is scheduled for App `__aexit__` (sync or async `close()` is accepted; coroutine returns are awaited).
4. None of the above: no teardown is registered for that singleton.

Passing `teardown=` SHALL raise `TypeError` whose message names the removal (`v0.35`) and points at the auto-detection rules.

#### Scenario: `__aexit__` auto-detected

- **GIVEN** `class DB: async def __aenter__(self): ...; async def __aexit__(self, *exc): ...` registered via `app.singleton(DB)`
- **WHEN** `async with app:` enters and then exits
- **THEN** `DB.__aenter__` ran once during App `__aenter__`
- **AND** `DB.__aexit__` ran once during App `__aexit__`

#### Scenario: `aclose` auto-detected

- **GIVEN** a singleton instance with no `__aexit__` but with `async def aclose(self): ...`
- **WHEN** App `__aexit__` runs
- **THEN** `instance.aclose()` was awaited exactly once

#### Scenario: `teardown=` kwarg raises

- **WHEN** `app.singleton(DB, factory, teardown=lambda d: d.close())` is called
- **THEN** `TypeError` is raised whose message contains `"teardown="` and `"__aexit__"`

### Requirement: Teardown order is topological (dependents before dependencies)

Singleton entries SHALL be ordered topologically by the DI graph at App `__aenter__`: dependencies enter before dependents. App `__aexit__` SHALL unwind in reverse order: dependents exit before dependencies. The topology SHALL be derived from the existing factory-parameter graph; pure types with no provider edges SHALL preserve registration order as the tiebreaker.

#### Scenario: Dependent enters after dependency

- **GIVEN** singleton `DB` and singleton `Repo(db: DB)` registered in that order
- **WHEN** `async with app:` enters
- **THEN** `DB.__aenter__` ran before `Repo.__aenter__`

#### Scenario: Dependent exits before dependency

- **GIVEN** the same setup
- **WHEN** the `async with` block exits
- **THEN** `Repo.__aexit__` ran before `DB.__aexit__`

### Requirement: Teardown without lifespan still fires

Every registered singleton with a detected cleanup protocol SHALL have that cleanup invoked when the enclosing `async with app:` block exits — there is no separate "no lifespan registered" code path because every App is now its own async context manager.

#### Scenario: App with only singletons unwinds correctly

- **GIVEN** an App with one singleton `DB` and no other lifecycle work
- **WHEN** `async with app: ...` runs to completion
- **THEN** `DB.__aenter__` ran on entry and `DB.__aexit__` ran on exit

## REMOVED Requirements

### Requirement: Sync `resolve` of an unresolved async singleton raises a precise error

**Reason**: under the new model, App `__aenter__` resolves and enters every singleton eagerly. There is no first-resolve-on-dispatch path for sync `resolve` to land on an unresolved async singleton. The precise-error guarantee is preserved through standard `AttributeError` / `RuntimeError` flow; the spec-level requirement is no longer load-bearing.

### Requirement: Async-factory singletons coalesce concurrent first-resolution

**Reason**: with eager App-entry resolution, there is no concurrent first-resolution race for singletons. Concurrent first-touch coalescing moves to **routers** (which enter lazily on first dispatch) and is documented in `router-conventions`.
