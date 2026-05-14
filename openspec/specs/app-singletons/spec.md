# app-singletons Specification

## Purpose
TBD - created by archiving change app-lifecycle-and-di-ergonomics. Update Purpose after archive.
## Requirements
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

### Requirement: Singletons resolve via the request-scoped container

A registered singleton SHALL be reachable via `container.resolve(T)` exactly like a `provide`-registered type. The container SHALL receive the cached instance on every resolve after the first. Resolution is synchronous.

#### Scenario: Singleton resolved twice returns the same instance

- **GIVEN** `app.singleton(AppState, factory)` where `factory` returns a fresh instance each time it is called
- **WHEN** the container resolves `AppState` twice (across two dispatches or two `resolve` calls)
- **THEN** both resolves return the same object
- **AND** `factory` was invoked exactly once

#### Scenario: Singleton dependency chains

- **GIVEN** `app.singleton(AppState, lambda settings: AppState(settings))` and `app.provide(Settings, load_settings)` (both sync)
- **WHEN** a tool method declares `state: AppState`
- **THEN** the container resolves `Settings` (per-dispatch), then resolves `AppState` once via the lambda
- **AND** subsequent dispatches reuse the cached `AppState` and do not re-call the factory

### Requirement: Singletons are App-scoped, not process-scoped

Two distinct `App` instances in the same process, each registering `singleton(T, ...)`, SHALL produce two distinct cached instances of `T`. The cache lives on the `App`, not on `T` and not in any process-global storage. This holds for both sync and async factory shapes; per-type locks for async coalescing live on the `Container`, not in process-global state.

#### Scenario: Two Apps, two singleton instances (sync)

- **GIVEN** `app_a = App("a").singleton(AppState, factory_a)` and `app_b = App("b").singleton(AppState, factory_b)`
- **WHEN** both Apps resolve `AppState`
- **THEN** the instance bound to `app_a`'s dispatch is distinct from the instance bound to `app_b`'s dispatch

#### Scenario: Two Apps, two singleton instances (async)

- **GIVEN** `app_a.singleton(SqliteResource, build_sqlite_async)` and `app_b.singleton(SqliteResource, build_sqlite_async)` registered with the same async factory function
- **WHEN** both Apps trigger async resolution of `SqliteResource`
- **THEN** the factory is awaited once per App
- **AND** each App caches its own distinct instance

### Requirement: Introspection surface

The `App` class SHALL expose `has_singleton(type_) -> bool` and `singletons() -> dict[type, Any]`. `has_singleton` SHALL return `True` once a singleton has been registered (before or after first resolve), regardless of whether the factory is sync or async. `singletons()` SHALL return a snapshot dict mapping registered types to their cached instances (or to a documented sentinel value for not-yet-resolved entries, which applies equally to async-factory singletons that have not yet been awaited).

#### Scenario: has_singleton before resolution (sync factory)

- **GIVEN** `app.singleton(AppState, factory)` registered with a sync factory but not yet resolved
- **WHEN** test code calls `app.has_singleton(AppState)`
- **THEN** the call returns `True`

#### Scenario: has_singleton before resolution (async factory)

- **GIVEN** `app.singleton(SqliteResource, build_sqlite_async)` registered with an async factory but not yet awaited
- **WHEN** test code calls `app.has_singleton(SqliteResource)`
- **THEN** the call returns `True`
- **AND** `app.singletons()[SqliteResource]` is the documented unresolved sentinel

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

### Requirement: Teardown failures are error-isolated

A teardown that raises `Exception` SHALL NOT prevent sibling teardowns from running. The framework SHALL catch the exception, record it on `App.teardown_failures` as `(type, exc)`, emit an `error`-level Python log line with the exception class, message, and singleton type name, and continue invoking the remaining teardowns in order. The framework SHALL NOT re-raise teardown exceptions from `lifespan_cm()`.

#### Scenario: One teardown raises; others still run; failure recorded

- **GIVEN** three singletons `A`, `B`, `C` each with a teardown; `B`'s teardown raises `RuntimeError("boom")`
- **WHEN** the App's lifespan exits
- **THEN** `A`'s and `C`'s teardowns both run (regardless of order between them and B)
- **AND** `app.teardown_failures` contains exactly one tuple `(B, RuntimeError("boom"))`
- **AND** an `error`-level log line was emitted naming `B` and the exception

### Requirement: Teardown without lifespan still fires

Every registered singleton with a detected cleanup protocol SHALL have that cleanup invoked when the enclosing `async with app:` block exits — there is no separate "no lifespan registered" code path because every App is now its own async context manager.

#### Scenario: App with only singletons unwinds correctly

- **GIVEN** an App with one singleton `DB` and no other lifecycle work
- **WHEN** `async with app: ...` runs to completion
- **THEN** `DB.__aenter__` ran on entry and `DB.__aexit__` ran on exit

### Requirement: Cycle in the singleton factory-parameter graph is handled deterministically

If the registered-singletons-with-teardowns subgraph contains a cycle (which the container's resolution-cycle detection should prevent in practice), `teardown_order()` SHALL break the cycle by emitting the lowest-`id` type and continuing, AND emit a `WARN`-level log line identifying the cycle and the break point.

#### Scenario: Cycle break is deterministic

- **GIVEN** a synthetic registration where two singletons mutually reference each other as factory parameters (constructed by direct provider manipulation in a test)
- **WHEN** `teardown_order()` is invoked
- **THEN** the call returns both types in a deterministic order (lowest-`id` first)
- **AND** a `WARN` log line is emitted identifying the cycle members and the break point

