# app-lifecycle Specification

## Purpose
TBD - created by archiving change app-lifecycle-and-di-ergonomics. Update Purpose after archive.
## Requirements
### Requirement: App SHALL implement the async context manager protocol

**Reshaped: `__aenter__` no longer triggers eager singleton entry; resources enter lazily on first dispatch.** The `a2kit.App` class SHALL implement `__aenter__` and `__aexit__`. `async with app:` SHALL be the canonical entry point for the App's lifecycle. App construction (`a2kit.App(...)` plus subsequent `add_router(...)` / `provide(...)` calls) SHALL be pure: no async work, no resource entry, no factory invocation.

The first `__aenter__` invocation on the App SHALL:

1. Run **graph validation** over the registered providers: every factory parameter SHALL resolve to a registered provider (or be auto-resolvable as a `BaseSettings` subclass); per-call factories MAY depend on app-scope but app-scope MAY NOT depend on per-call (rejected with `TypeError`).
2. Seal the container against further `provide(...)` calls (subsequent registration raises).
3. Return control to the lifespan body.

The first `__aenter__` SHALL NOT enter any registered resource. Resources enter lazily on first dispatch that resolves them through the container (see `app-singletons`).

`__aexit__` SHALL unwind the App-scope cleanup stack via the LIFO + per-resource isolation contract (see `di-scope-cleanup-stack`).

**Multiplexed serve.** When a single process serves more than one surface from the same `App` (see `serve-topology`), the `App` lifecycle SHALL be entered exactly once for the process. A single `async with app:` SHALL span the whole process and SHALL be owned by the parent application that mounts the surfaces, not by any individual surface's lifespan. No mounted surface SHALL call `App.__aexit__`; the cleanup stack and the DI container are process-wide shared state, and a per-surface exit would drain them while another surface is still serving.

#### Scenario: Construction is pure

- **GIVEN** `app = a2kit.App("api")` followed by `app.provide(DB)` and `app.add_router(Github())`
- **WHEN** the constructor and registration calls return
- **THEN** no `__aenter__` method on any resource or Router has been invoked
- **AND** no factory has been called

#### Scenario: `async with app` does not enter resources eagerly

- **GIVEN** an App with `app.provide(A)` and `app.provide(B)` (both implementing `__aenter__`/`__aexit__`)
- **WHEN** `async with app:` is entered and the lifespan body runs without dispatching any tool that needs `A` or `B`
- **THEN** neither `A.__aenter__` nor `B.__aenter__` has been invoked

#### Scenario: First dispatch enters dependency before dependent

- **GIVEN** `app.provide(A)` and `app.provide(B)` where `B`'s factory declares `A` as a parameter
- **WHEN** the first dispatch resolves `B`
- **THEN** `A.__aenter__` ran before `B.__aenter__`
- **AND** the App-scope cleanup stack records `A` before `B` (insertion order = resolution order)

#### Scenario: `async with app` exit unwinds resolved resources in LIFO order

- **GIVEN** an App where dispatches have caused `A`, `B`, `C` to enter in that order
- **WHEN** the `async with` block exits normally
- **THEN** `C.__aexit__` ran first, then `B.__aexit__`, then `A.__aexit__`

#### Scenario: Lifespan body may force-resolve for start-time verification

- **GIVEN** an App where the operator needs `SqliteResource` to be verified at start
- **WHEN** the lifespan body runs `await app._resolver.get(SqliteResource)` between `async with app:` and the App being served
- **THEN** `SqliteResource.__aenter__` runs at start (loud failure if DB is unreachable)
- **AND** subsequent dispatches receive the cached instance

#### Scenario: Graph validation rejects scope violation

- **GIVEN** `app.provide(Foo, foo_factory)` where `foo_factory(bar: Bar)` and `app.provide(Bar, bar_factory, per_call=True)`
- **WHEN** `async with app:` is entered
- **THEN** `TypeError` is raised before any tool dispatches
- **AND** the message names `"Foo"`, `"Bar"`, and `"app-scope depends on per-call"`

#### Scenario: Sealed container rejects late `provide`

- **GIVEN** an App that has entered (`async with app:` body is running)
- **WHEN** `app.provide(SomeType, factory)` is called inside the lifespan body
- **THEN** `TypeError` is raised
- **AND** the message names the sealing rule and the test-override pattern (composition-root re-registration before `async with`)

#### Scenario: Multiplexed serve enters the App lifecycle once

- **GIVEN** a single process serving both the MCP and REST surfaces from one `App`
- **WHEN** the server starts and then shuts down
- **THEN** `async with app:` was entered exactly once, owned by the parent application
- **AND** neither the MCP nor the REST mount invoked `App.__aexit__`

### Requirement: `App.__init__` SHALL reject the removed `lifespan=` kwarg with a migration hint

`App.__init__` SHALL accept `**_kw: Any` after its documented positional + keyword parameters. If `_kw` contains `lifespan` the constructor SHALL raise `TypeError` whose message names `App(lifespan=...)`, the version of removal (`v0.35`), and points at the two replacement paths: (a) a marker resource with `__aenter__`/`__aexit__`, (b) imperative work in `main()` before `async with app:`. Other unknown kwargs SHALL raise `TypeError` with the standard "unexpected kwarg" shape.

#### Scenario: `lifespan=` raises with hint

- **WHEN** `a2kit.App("x", lifespan=some_cm)` is constructed
- **THEN** `TypeError` is raised whose message contains both the string `"lifespan="` and the string `"__aenter__"`

#### Scenario: Documented kwargs still work

- **WHEN** `a2kit.App("x", debug=True)` is constructed
- **THEN** no `TypeError` is raised and the App is usable

### Requirement: Singleton or router `__aexit__` failure SHALL log and continue unwinding

If a resource's `__aexit__` (or factory `finally` block) raises during App `__aexit__`, the framework SHALL log the exception at level WARN with traceback, SHALL continue unwinding remaining entries in LIFO order, and SHALL NOT re-raise unless the original `__aexit__` was called with a non-None exception (in which case the in-flight exception SHALL win and the swallowed cleanup error SHALL still be logged). This is the App-lifecycle expression of the LIFO + per-resource isolation contract owned by `di-scope-cleanup-stack`; the cleanup-stack capability is canonical for the unwind semantics, and the cleanup machinery lives under the `a2kit.packages.di` module.

#### Scenario: Cleanup error logged, sibling unwind continues

- **GIVEN** resources `A` (well-behaved), `B` (raises in `__aexit__`), `C` (well-behaved), all entered during dispatches
- **WHEN** App `__aexit__` runs
- **THEN** `C.__aexit__` ran, `B.__aexit__` raised and was logged at WARN, `A.__aexit__` ran
- **AND** the `async with app:` block exited without raising

#### Scenario: In-flight error is preserved when cleanup also raises

- **GIVEN** the `async with app:` body raised `ValueError("x")` and resource `B`'s `__aexit__` raises `RuntimeError("y")` during the unwind
- **WHEN** the `async with` block exits
- **THEN** the caller sees the in-flight `ValueError("x")`
- **AND** `RuntimeError("y")` was logged at WARN and not re-raised

