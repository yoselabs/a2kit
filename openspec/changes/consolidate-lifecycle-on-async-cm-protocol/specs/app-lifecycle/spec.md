# app-lifecycle — consolidate-lifecycle-on-async-cm-protocol delta

The canonical `app-lifecycle` spec still describes the pre-archive
`on_startup`/`on_shutdown` surface (carry-over from the
`app-lifecycle-and-di-ergonomics` archive; later removed by
`lifespan-over-lifecycle-hooks` but not re-stamped here). This delta
removes those stale requirements and adds the post-consolidation
shape: `a2kit.App` is its own async context manager; composition is
internal via `AsyncExitStack`; there is no `lifespan=` constructor
argument.

## REMOVED Requirements

### Requirement: App exposes `on_startup` and `on_shutdown` registration

**Reason**: removed in v0.32 by `lifespan-over-lifecycle-hooks`; this delta clears the stale entry from the canonical spec.

### Requirement: Lifecycle handlers resolve kwargs via the container

**Reason**: removed in v0.32 by `lifespan-over-lifecycle-hooks`; handlers themselves no longer exist as a registration target.

### Requirement: Both transports invoke handlers exactly once per process / lifespan

**Reason**: superseded by `async with app:` semantics that are themselves the once-per-lifespan guarantee.

### Requirement: Shutdown handlers run in reverse registration order

**Reason**: replaced by `AsyncExitStack` LIFO unwind of the singleton + router stack — see the new requirement below.

### Requirement: Startup failure aborts lifecycle and propagates

**Reason**: same — `AsyncExitStack` semantics propagate the first startup failure and unwind already-entered legs. The behavior is preserved; the spec phrasing moves to the new requirement.

### Requirement: Shutdown failure is logged and swallowed; remaining handlers still run

**Reason**: behavior preserved as "singleton/router `__aexit__` failures log + continue unwind"; the spec phrasing moves to the new requirement.

### Requirement: Sync handlers are accepted and run inline

**Reason**: handler registration removed entirely.

## ADDED Requirements

### Requirement: App SHALL implement the async context manager protocol

The `a2kit.App` class SHALL implement `__aenter__` and `__aexit__`. `async with app:` SHALL be the canonical entry point for the App's lifecycle. App construction (`a2kit.App(...)` plus subsequent `add_router(...)` / `singleton(...)` calls) SHALL be pure: no async work, no singleton `__aenter__`, no router `__aenter__`. The first `__aenter__` invocation on the App SHALL be the only event that triggers framework-owned resource entry.

#### Scenario: Construction is pure

- **GIVEN** `app = a2kit.App("api")` followed by `app.singleton(DB)` and `app.add_router(Github())`
- **WHEN** the constructor and registration calls return
- **THEN** no `__aenter__` method on any singleton or Router has been invoked

#### Scenario: `async with app` enters singletons

- **GIVEN** an App with singletons `A`, `B` registered (no DI relationship)
- **WHEN** `async with app:` is entered
- **THEN** both `A.__aenter__` and `B.__aenter__` have been invoked exactly once before the body runs

#### Scenario: `async with app` exit unwinds in LIFO order

- **GIVEN** an App with singletons `A`, `B` entered during `__aenter__`
- **WHEN** the `async with` block exits normally
- **THEN** `B.__aexit__` ran before `A.__aexit__`

### Requirement: `App.__init__` SHALL reject the removed `lifespan=` kwarg with a migration hint

`App.__init__` SHALL accept `**_kw: Any` after its documented positional + keyword parameters. If `_kw` contains `lifespan` the constructor SHALL raise `TypeError` whose message names `App(lifespan=...)`, the version of removal (`v0.35`), and points at the two replacement paths: (a) a marker singleton with `__aenter__`/`__aexit__`, (b) imperative work in `main()` before `async with app:`. Other unknown kwargs SHALL raise `TypeError` with the standard "unexpected kwarg" shape.

#### Scenario: `lifespan=` raises with hint

- **WHEN** `a2kit.App("x", lifespan=some_cm)` is constructed
- **THEN** `TypeError` is raised whose message contains both the string `"lifespan="` and the string `"__aenter__"`

#### Scenario: Documented kwargs still work

- **WHEN** `a2kit.App("x", debug=True)` is constructed
- **THEN** no `TypeError` is raised and the App is usable

### Requirement: Composition SHALL be internal via AsyncExitStack

The framework SHALL compose singleton entries, router entries, and any framework-owned cleanup callbacks via a single `contextlib.AsyncExitStack` owned by the App. The composed unwind order SHALL be LIFO. Composition SHALL NOT be a public surface: there is no `a2kit.lifespan.compose`, no `app.use(cm)`, no `App(lifespan=...)`.

#### Scenario: Public composition surface absent

- **WHEN** `grep -rn "lifespan.compose\|app.use(\|App(.*lifespan=" src/` runs (excluding test fixtures asserting the migration error)
- **THEN** the result is empty

### Requirement: Singleton or router `__aexit__` failure SHALL log and continue unwinding

If a singleton's or Router's `__aexit__` raises during App `__aexit__`, the framework SHALL log the exception via `logging.getLogger("a2kit.lifecycle")` at level ERROR with traceback, SHALL continue unwinding remaining entries, and SHALL NOT re-raise unless the original `__aexit__` was called with a non-None exception (in which case the in-flight exception SHALL win and the swallowed shutdown error SHALL still be logged).

#### Scenario: Shutdown error logged, sibling unwind continues

- **GIVEN** singletons `A` (well-behaved), `B` (raises in `__aexit__`), `C` (well-behaved), all entered
- **WHEN** App `__aexit__` runs
- **THEN** `C.__aexit__` ran, `B.__aexit__` raised and was logged at ERROR, `A.__aexit__` ran
- **AND** the `async with app:` block exited without raising

#### Scenario: Tool error is preserved when shutdown also raises

- **GIVEN** the `async with app:` body raised `ToolError("x")` and singleton `B.__aexit__` raises `ShutdownError("y")`
- **WHEN** the `async with` block exits
- **THEN** the caller sees `ToolError("x")`
- **AND** `ShutdownError("y")` was logged at ERROR
