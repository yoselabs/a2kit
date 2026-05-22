## MODIFIED Requirements

### Requirement: App SHALL implement the async context manager protocol

The sealed-runtime **`AppRuntime`** class SHALL implement `__aenter__` and `__aexit__`. `AppRuntime` is internal: it is produced by a finisher's internal `build(app)` step and is never exported on the `a2kit.*` surface. The compose-phase `a2kit.App` SHALL NOT implement the async context manager protocol. A finisher (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`) SHALL be the canonical consumer entry point; consumers SHALL NOT construct or enter an `AppRuntime` directly.

App construction (`a2kit.App(...)` plus subsequent `add_router(...)` / `provide(...)` calls) SHALL be pure: no async work, no resource entry, no factory invocation.

A finisher's `build(app)` step SHALL:

1. Run **graph validation** over the App's registered providers: every factory parameter SHALL resolve to a registered provider (or be auto-resolvable as a `BaseSettings` subclass); per-call factories MAY depend on app-scope but app-scope MAY NOT depend on per-call (rejected with `TypeError`).
2. Snapshot the App's provider registrations and wire-scopes into a **fresh** `Container` owned by the resulting `AppRuntime`. The App's own compose-phase container SHALL be left untouched, so the App remains a reusable builder.
3. Return an `AppRuntime`.

The first `__aenter__` invocation on the `AppRuntime` SHALL NOT enter any registered resource. Resources enter lazily on first dispatch that resolves them through the container (see `app-singletons`).

`__aexit__` SHALL unwind the App-scope cleanup stack via the LIFO + per-resource isolation contract (see `di-scope-cleanup-stack`).

**Multiplexed serve.** When a single process serves more than one surface from the same `App` (see `serve-topology`), the `AppRuntime` lifecycle SHALL be entered exactly once for the process. A single `async with runtime:` SHALL span the whole process and SHALL be owned by the parent application that mounts the surfaces, not by any individual surface's lifespan. No mounted surface SHALL call `AppRuntime.__aexit__`; the cleanup stack and the DI container are process-wide shared state, and a per-surface exit would drain them while another surface is still serving.

#### Scenario: Construction is pure

- **GIVEN** `app = a2kit.App("api")` followed by `app.provide(DB)` and `app.add_router(Github())`
- **WHEN** the constructor and registration calls return
- **THEN** no `__aenter__` method on any resource or Router has been invoked
- **AND** no factory has been called

#### Scenario: AppRuntime entry does not enter resources eagerly

- **GIVEN** an App with `app.provide(A)` and `app.provide(B)` (both implementing `__aenter__`/`__aexit__`), handed to a finisher
- **WHEN** the finisher's `AppRuntime` is entered and the lifespan body runs without dispatching any tool that needs `A` or `B`
- **THEN** neither `A.__aenter__` nor `B.__aenter__` has been invoked

#### Scenario: First dispatch enters dependency before dependent

- **GIVEN** `app.provide(A)` and `app.provide(B)` where `B`'s factory declares `A` as a parameter
- **WHEN** the first dispatch resolves `B`
- **THEN** `A.__aenter__` ran before `B.__aenter__`
- **AND** the App-scope cleanup stack records `A` before `B` (insertion order = resolution order)

#### Scenario: AppRuntime exit unwinds resolved resources in LIFO order

- **GIVEN** an `AppRuntime` where dispatches have caused `A`, `B`, `C` to enter in that order
- **WHEN** the `async with runtime:` block exits normally
- **THEN** `C.__aexit__` ran first, then `B.__aexit__`, then `A.__aexit__`

#### Scenario: Lifespan body may force-resolve for start-time verification

- **GIVEN** an `AppRuntime` where the operator needs `SqliteResource` to be verified at start
- **WHEN** the lifespan body runs `await runtime._resolver.get(SqliteResource)` between entering the `AppRuntime` and it being served
- **THEN** `SqliteResource.__aenter__` runs at start (loud failure if DB is unreachable)
- **AND** subsequent dispatches receive the cached instance

#### Scenario: Graph validation rejects scope violation

- **GIVEN** `app.provide(Foo, foo_factory)` where `foo_factory(bar: Bar)` and `app.provide(Bar, bar_factory, per_call=True)`
- **WHEN** a finisher's `build(app)` step runs
- **THEN** `TypeError` is raised before any `AppRuntime` is produced
- **AND** the message names `"Foo"`, `"Bar"`, and `"app-scope depends on per-call"`

#### Scenario: Multiplexed serve enters the AppRuntime lifecycle once

- **GIVEN** a single process serving both the MCP and REST surfaces from one `App`
- **WHEN** the server starts and then shuts down
- **THEN** the `AppRuntime` was entered exactly once, owned by the parent application
- **AND** neither the MCP nor the REST mount invoked `AppRuntime.__aexit__`

### Requirement: Singleton or router `__aexit__` failure SHALL log and continue unwinding

If a resource's `__aexit__` (or factory `finally` block) raises during `AppRuntime.__aexit__`, the framework SHALL log the exception at level WARN with traceback, SHALL continue unwinding remaining entries in LIFO order, and SHALL NOT re-raise unless the original `__aexit__` was called with a non-None exception (in which case the in-flight exception SHALL win and the swallowed cleanup error SHALL still be logged). This is the App-lifecycle expression of the LIFO + per-resource isolation contract owned by `di-scope-cleanup-stack`; the cleanup-stack capability is canonical for the unwind semantics, and the cleanup machinery lives under the `a2kit.packages.di` module.

#### Scenario: Cleanup error logged, sibling unwind continues

- **GIVEN** resources `A` (well-behaved), `B` (raises in `__aexit__`), `C` (well-behaved), all entered during dispatches
- **WHEN** `AppRuntime.__aexit__` runs
- **THEN** `C.__aexit__` ran, `B.__aexit__` raised and was logged at WARN, `A.__aexit__` ran
- **AND** the `async with runtime:` block exited without raising

#### Scenario: In-flight error is preserved when cleanup also raises

- **GIVEN** the `async with runtime:` body raised `ValueError("x")` and resource `B`'s `__aexit__` raises `RuntimeError("y")` during the unwind
- **WHEN** the `async with` block exits
- **THEN** the caller sees the in-flight `ValueError("x")`
- **AND** `RuntimeError("y")` was logged at WARN and not re-raised
