## MODIFIED Requirements

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
