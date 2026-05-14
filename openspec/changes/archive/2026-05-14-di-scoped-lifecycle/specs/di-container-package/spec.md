# di-container-package delta

## MODIFIED Requirements

### Requirement: DI container lives at `a2kit.packages.di`

The DI container module SHALL live at `src/a2kit/packages/di/`. The package SHALL be **self-contained**: no `a2kit.*` imports inside the `a2kit/packages/di/` tree. A static lint check SHALL enforce this discipline. The package SHALL be structured to enable future extraction to a standalone PyPI distribution (separate `pyproject.toml` skeleton present, but the actual publish is out of scope for this change).

All a2kit modules that need container types, the `Resolver` protocol, or the `Scope` enum SHALL import from `a2kit.packages.di`. The file at `src/a2kit/packages/connections/container.py` SHALL NOT exist (carryover from prior change).

#### Scenario: Container module is importable standalone

- **WHEN** a script outside the `a2kit` package tree imports `a2kit.packages.di`
- **THEN** the import succeeds
- **AND** `Container`, `Scope`, `Resolver`, `UnresolvableType` are accessible

#### Scenario: No a2kit imports inside the package

- **WHEN** `grep -rn "^from a2kit\|^import a2kit" src/a2kit/packages/di/` runs (excluding the `a2kit.packages.di.*` self-references)
- **THEN** the result is empty
- **AND** the lint check `a2kit lint static` enforces this with a dedicated rule code

#### Scenario: Old import path is gone (carryover)

- **WHEN** a script tries `from a2kit.packages.connections.container import Container`
- **THEN** the import fails with `ModuleNotFoundError` or equivalent

### Requirement: Container references no feature names

The container module SHALL NOT contain any reference (in code, docstrings, or attribute names) to features built on top of it. Specifically: no `"connection"`, no `_chain_reaches_connection`, no `needs_connection`, no `install_connection_providers`. The container also SHALL NOT reference `pydantic_settings` by direct import; auto-resolution of `BaseSettings` subclasses (see `app-singletons`) is implemented via duck-typing (`hasattr` + inheritance walk) so the container remains usable without pydantic installed.

#### Scenario: Source grep for feature names

- **WHEN** the source of `a2kit/packages/di/` is grepped for `"connection"`, `"tracker"`, `"tenant"`, `"pydantic"`, or any other feature-suggestive string
- **THEN** no matches are found in code or attribute names (docstrings that explicitly enumerate "this container has no feature awareness" as the contract are the only allowed mentions)

### Requirement: Public surface is small and synchronous

**Reshaped: the surface gains async resolution, scope hierarchy, child containers, and the `Resolver` protocol. Sync resolution remains available for the synchronous fast path within the same scope.** The container's public surface SHALL consist of:

- **`Container` class** with methods: `register(t, factory, *, scope: Scope = Scope.SINGLETON)`, `has(t) -> bool`, `providers() -> dict`, `resolve(t)` (sync), async `get(t)` (the canonical async path that may run `__aenter__` / await factories), `child() -> Container` (returns a fresh scoped child), `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`. Plus async context manager protocol (`__aenter__` / `__aexit__`) on the `Container` itself, where exit triggers the cleanup stack unwind for this scope.
- **`Scope` enum** with values `SINGLETON`, `SCOPED`, `TRANSIENT`. `Container` scope-routing semantics: `SINGLETON` caches at root, `SCOPED` caches at the immediate child, `TRANSIENT` returns a fresh resolution each call.
- **`Resolver` Protocol** declaring the narrow surface a2kit framework modules use: `async get[T](t: type[T]) -> T`, `def provide(t, factory=None, *, scope: Scope = Scope.SINGLETON) -> None`, `def child() -> Resolver`, `async def aclose() -> None`.
- **`UnresolvableType` exception** (carryover).

Sync `Container.resolve(t)` SHALL remain for the hot path within a scope but SHALL raise `ValueError` if asked to resolve an async-factory app-scope type whose factory has not yet been awaited (carryover from the async-singleton lock-coalesce contract).

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

#### Scenario: `Resolver` protocol is a typing.Protocol

- **WHEN** `Resolver` is inspected via `typing.get_origin` / `runtime_checkable`
- **THEN** it is a `typing.Protocol` class
- **AND** `isinstance(container, Resolver)` is `True` for a default `Container` instance (via `@runtime_checkable`)

### Requirement: Container exposes a sealed test-only snapshot/restore pair

**Reshaped: snapshot/restore covers the expanded internal state (providers, app-scope cache, async factories, **cleanup stack**, scope metadata). Test code SHALL prefer composition-root re-registration over snapshot/restore; the snapshot pair is retained for fine-grained test isolation where re-registration would be too coarse.** The `Container` class SHALL provide two methods, `_snapshot()` and `_restore(snapshot)`. The methods SHALL:

- be synchronous,
- be feature-agnostic (no references to specific feature names),
- be prefixed with a single underscore to signal "test-only, not part of the documented public surface",
- preserve the rest of the documented public surface unchanged.

`_snapshot()` SHALL return an opaque value capturing the current `_providers`, `_app_cache`, `_async_factories`, `_cleanup_stack`, AND `_scope_metadata` state (shallow copies of each). `_restore(snapshot)` SHALL replace those structures with the snapshot's contents, discarding any intervening mutations. The hot-path `resolve` and `get` methods SHALL NOT branch on test-only state; snapshot/restore SHALL achieve override semantics by mutating the existing structures, not by introducing a separate override layer consulted on every resolve.

#### Scenario: Snapshot captures all internal state

- **GIVEN** a Container with multiple providers registered (sync and async, singleton and scoped) and the app-scope cache partially populated
- **WHEN** test code calls `snap = container._snapshot()`, mutates several pieces of state, and then calls `container._restore(snap)`
- **THEN** the container's `_providers`, `_app_cache`, `_async_factories`, `_cleanup_stack`, and `_scope_metadata` are returned to the exact state captured by `snap`

#### Scenario: Snapshot/restore is feature-agnostic

- **WHEN** the source of `_snapshot` / `_restore` is read
- **THEN** the code contains no reference to feature names (`"connection"`, `"tracker"`, etc.) — only the generic structure capture/replace

#### Scenario: Resolve hot path is untouched

- **WHEN** the `Container.resolve` and `Container.get` method bodies are read after this change
- **THEN** they contain no branch that consults a `_overrides` map or other test-only side state; override semantics are implemented entirely by mutating the captured structures through the snapshot pair

## ADDED Requirements

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

The `Container` class SHALL implement `__aenter__` and `__aexit__`. Entering the container SHALL be a no-op (lazy resolution defers all work to first `get`). Exiting the container SHALL unwind its own cleanup stack via the LIFO + per-resource isolation contract. The `App.__aexit__` SHALL exit the root container by leveraging this protocol.

#### Scenario: Root container exit unwinds cleanup stack

- **WHEN** `async with container:` exits a root container that has resources `A`, `B`, `C` on its cleanup stack
- **THEN** cleanup runs in LIFO order (`C`, then `B`, then `A`)
- **AND** per-resource exception isolation is enforced (see `di-scope-cleanup-stack`)
