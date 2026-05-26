# di-container-package Specification

## Purpose
TBD - created by archiving change di-sync-and-unleak. Update Purpose after archive.
## Requirements
### Requirement: DI container lives at `a2kit.packages.di`

The DI container module SHALL live at `src/a2kit/packages/di/`.
The package SHALL be **self-contained**: no `a2kit.*` imports inside the `a2kit/packages/di/` tree. A static lint check SHALL enforce this discipline. The package SHALL be structured to enable future extraction to a standalone PyPI distribution (separate `pyproject.toml` skeleton present, but the actual publish is out of scope for this change).

All a2kit modules that need container types, the `Resolver` protocol, or the `Scope` enum SHALL import from `a2kit.packages.di`.

#### Scenario: Container module is importable standalone

- **WHEN** a script outside the `a2kit` package tree imports `a2kit.packages.di`
- **THEN** the import succeeds
- **AND** `Container`, `Scope`, `Resolver`, `UnresolvableType` are accessible

#### Scenario: No a2kit imports inside the package

- **WHEN** `grep -rn "^from a2kit\|^import a2kit" src/a2kit/packages/di/` runs (excluding the `a2kit.packages.di.*` self-references)
- **THEN** the result is empty
- **AND** the lint check `a2kit lint static` enforces this with a dedicated rule code

#### Scenario: Container resolution types resolve from the package root

- **WHEN** a consumer imports the container surface from `a2kit.packages.di`
- **THEN** `Container`, `Scope`, `Resolver`, and `UnresolvableType` all resolve from that single package root
- **AND** no other module path exposes those container types

### Requirement: Container references no feature names

The container module SHALL NOT contain any reference (in code, docstrings, or attribute names) to features built on top of it. Specifically: no `"connection"`, no `_chain_reaches_connection`, no `needs_connection`, no `install_connection_providers`. The container also SHALL NOT reference `pydantic_settings` by direct import; auto-resolution of `BaseSettings` subclasses (see `app-singletons`) is implemented via duck-typing (`hasattr` + inheritance walk) so the container remains usable without pydantic installed.

#### Scenario: Source grep for feature names

- **WHEN** the source of `a2kit/packages/di/` is grepped for `"connection"`, `"tracker"`, `"tenant"`, `"pydantic"`, or any other feature-suggestive string
- **THEN** no matches are found in code or attribute names (docstrings that explicitly enumerate "this container has no feature awareness" as the contract are the only allowed mentions)

### Requirement: Public surface is small and synchronous

The public surface of `Container` SHALL remain small and consist of
documented methods only. Adding `seed_scoped(type_, value)` extends
the surface to the following public methods:

- `provide(type_, factory=None, *, scope=Scope.SINGLETON) -> None`
- `seed_scoped(type_, value) -> None` (new; child containers only)
- `has_provider(type_) -> bool`
- `child() -> Container`
- `call_scope(fn, wire_kwargs=None, *, pre_hook=None) -> AsyncContextManager`
- `expose_as_fastapi_depends(type_) -> Callable`
- `providers_view() -> dict`
- `snapshot() -> Container`
- `seal() -> None`
- async lifecycle methods (`__aenter__`, `__aexit__`, `aclose`)

The internals (`_providers`, `_scope_metadata`, `_scoped_cache`,
`_parent`) SHALL NOT be considered public; tests and substrate
adapters touching them are accepted technical debt to be migrated
to documented APIs over time.

Sync `Container.resolve(t)` SHALL remain for the hot path within a scope but SHALL raise `ValueError` if asked to resolve an async-factory app-scope type whose factory has not yet been awaited.

#### Scenario: `seed_scoped` appears in the package's exported surface

- **WHEN** inspecting `a2kit.packages.di.Container`'s public methods
  (those without leading underscore)
- **THEN** `seed_scoped` is among them
- **AND** its docstring documents the child-only constraint

#### Scenario: Async `get` is the canonical resolution path

- **WHEN** `inspect.iscoroutinefunction(Container.get)` is checked
- **THEN** the result is `True`
- **AND** `Container.get(T)` may invoke `__aenter__` on the resolved instance and record cleanup on the scope's cleanup stack

#### Scenario: Sync `resolve` available for hot path

- **WHEN** `inspect.iscoroutinefunction(Container.resolve)` is checked
- **THEN** the result is `False`
- **AND** `resolve` is callable from sync code paths that operate within a single already-warmed scope

#### Scenario: `Scope` enum has the three documented values

- **WHEN** `list(Scope)` is enumerated
- **THEN** the result is `[Scope.SINGLETON, Scope.SCOPED, Scope.TRANSIENT]` (or equivalent ordering)
- **AND** `Scope.__module__` is `"a2kit.packages.di"`

#### Scenario: `register` is not a callable resolution method

- **WHEN** `Container.register` is invoked
- **THEN** it raises `TypeError` (a retired-name stub, per `request-scoped-di`) — it is not the registration path; `provide` is

#### Scenario: `dispatch` is not a callable method

- **WHEN** `Container.dispatch` is accessed
- **THEN** it does not resolve to the per-call scope helper — the method was renamed to `call_scope` and no alias is kept

### Requirement: `Container.seed_scoped(type_, value)` is the explicit per-call seed API

`Container.seed_scoped(type_, value) -> None` SHALL register `value`
as a SCOPED provider for `type_` on a child (per-call) container.
This is the framework's documented, explicit way to publish a
per-call typed instance into the DI scope.

- The method MUST be a no-op-free, single-line registration: providers
  dict + scope metadata + scoped cache.
- The method SHALL refuse to operate on a root container (i.e., a
  container with no `_parent`). Calling it raises `TypeError` with a
  message instructing the caller to open a child via
  `container.child()` or to call inside `call_scope`.
- Re-registration of the same `type_` within the same child scope
  follows last-write-wins (matches `Container.provide`).
- `seed_scoped` accepts an instance, not a factory. Per-call SCOPED
  factories are still registered via `Container.provide(type_,
  factory, scope=Scope.SCOPED)` at app construction.

#### Scenario: seed_scoped on a child registers a SCOPED provider

- **GIVEN** a root `Container` and a child opened via
  `container.child()`
- **WHEN** `child.seed_scoped(Principal, p)` is called with a
  `Principal` instance `p`
- **THEN** `await child.get(Principal)` returns `p`
- **AND** the provider metadata records `Scope.SCOPED`

#### Scenario: seed_scoped on a root raises

- **GIVEN** a root `Container` (no `_parent`)
- **WHEN** `container.seed_scoped(Principal, p)` is called
- **THEN** `TypeError` is raised
- **AND** the message names `child()` or `call_scope` as the correct
  entry point

#### Scenario: seed_scoped is last-write-wins per scope

- **GIVEN** a child with `seed_scoped(Principal, p1)`
- **WHEN** `seed_scoped(Principal, p2)` is called on the same child
- **THEN** `await child.get(Principal)` returns `p2`

### Requirement: `Container.child()` opens a fresh scoped sub-container

The `Container` class SHALL expose `child() -> Container` that returns a fresh sub-container whose lifetime is independent of the parent. The child SHALL share access to the parent's providers (so a `Scope.SINGLETON` registration on the parent is resolvable from the child), maintain its own cleanup stack for resources entered within its scope, and resolve `Scope.SCOPED` registrations from its own cache. The child SHALL implement the async context manager protocol; exiting the child via `async with` SHALL unwind its cleanup stack via the same LIFO + per-resource isolation contract as the root (see `di-scope-cleanup-stack`).

The dispatcher SHALL open one child per tool invocation (per-call scope) via `app._resolver.child()`. Closing the child SHALL NOT affect the parent's app-scope cache.

#### Scenario: Child resolves parent's singleton

- **GIVEN** `parent.register(ConnectionPool, factory, scope=Scope.SINGLETON)` and `child = parent.child()`
- **WHEN** `await child.get(ConnectionPool)` is called
- **THEN** the parent's factory is invoked (if not previously) and the result is cached on the parent
- **AND** the same instance is returned from `await parent.get(ConnectionPool)` thereafter

#### Scenario: Child's SCOPED registration is local

- **GIVEN** `child.register(Transaction, factory, scope=Scope.SCOPED)`
- **WHEN** `await child.get(Transaction)` is called
- **THEN** the factory is invoked and the result is cached on the child
- **AND** `await parent.get(Transaction)` raises `UnresolvableType` (parent does not see the child's registration)

#### Scenario: Closing a child unwinds only its cleanup stack

- **GIVEN** a child container with two entered SCOPED resources `A` and `B`, and a parent with one entered SINGLETON resource `C`
- **WHEN** `async with` exits the child
- **THEN** `B`'s cleanup runs, then `A`'s cleanup runs (LIFO on the child's stack)
- **AND** `C`'s cleanup does not run (parent's stack is untouched)

### Requirement: Container is async-context-manageable as a whole

The `Container` class SHALL implement `__aenter__` and `__aexit__`. Entering the container SHALL be a no-op (lazy resolution defers all work to first `get`). Exiting the container SHALL unwind its own cleanup stack via the LIFO + per-resource isolation contract. The `AppRuntime.__aexit__` SHALL exit the root container by leveraging this protocol.

#### Scenario: Root container exit unwinds cleanup stack

- **WHEN** `async with container:` exits a root container that has resources `A`, `B`, `C` on its cleanup stack
- **THEN** cleanup runs in LIFO order (`C`, then `B`, then `A`)
- **AND** per-resource exception isolation is enforced (see `di-scope-cleanup-stack`)

### Requirement: Container bridges to FastAPI `Depends` via `expose_as_fastapi_depends`

`Container` SHALL provide `expose_as_fastapi_depends(type_: type) -> Callable[..., Any]` returning a FastAPI-compatible resolver that reads the active `_a2kit_request_scope` contextvar. Generated callables SHALL be cached per (container, type) so identical-type calls return the same callable object.

#### Scenario: Container-known type resolvable via FastAPI Depends

- **GIVEN** a `Database` type registered with the a2kit container
- **AND** a FastAPI guard `def guard(db: Annotated[Database, Depends(Database)]) -> str: return db.name`
- **WHEN** an HTTP request reaches a route protected by `Security(guard)`
- **THEN** `guard` resolves `db` from the active a2kit call scope
- **AND** the same instance is visible to the route handler

### Requirement: Framework-owned providers are seeded at App construction

`App.__init__` SHALL seed the DI container with framework-owned
providers before any user `app.provide(...)` call is accepted. The
framework-owned providers SHALL include the full set of config types
(`A2kitConfig` plus each registered sub-config type). User
registrations made via `app.provide(...)` SHALL win over framework
defaults, per the standard last-write-wins semantics of the container
(ADR 0006).

#### Scenario: User override of LddConfig replaces framework default

- **GIVEN** a fresh `App`
- **WHEN** the user calls `app.provide(LddConfig, lambda: custom)`
- **AND** the runtime is built
- **THEN** resolving `LddConfig` from the container returns `custom`
- **AND** does NOT return the App's `config.ldd`

#### Scenario: Framework providers are present even without user calls

- **GIVEN** a fresh `App` with no user `.provide(...)` calls
- **WHEN** the runtime is built and `A2kitConfig` is resolved
- **THEN** the container returns the App's `config` instance

