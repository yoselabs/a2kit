# request-scoped-di — delta

## REMOVED Requirements

### Requirement: Synchronous resolve, no `connection` kwarg

**Reason:** The legacy synchronous `Container.resolve(type_)` is retired in v0.38. The new resolve path is async via `Container.get(type_)`, which honors `__aenter__` lifecycle, per-call scope, the cleanup stack, and `Lazy[T]`. A synchronous resolve cannot honor `__aenter__`, so it is incompatible with the v0.36 lifecycle model.

**Migration:** Replace `container.resolve(T)` with `await container.get(T)`. Test code calling the sync resolve in a non-async context migrates the test fixture to `pytest.mark.asyncio` or uses `asyncio.run(container.get(T))` at the call site.

## ADDED Requirements

### Requirement: Legacy DI methods raise `TypeError` with migration hints

`Container.register`, `Container.register_singleton`, `Container.resolve`, `Container.aresolve`, `Container.has`, `Container.has_async_singleton`, and `Container.has_any_async_singletons` SHALL raise `TypeError` when called. The error message MUST name the v0.38 replacement (`provide`, `get`, `has_provider`) and reference the CHANGELOG entry.

#### Scenario: legacy `register` raises with hint

- **GIVEN** a `Container` instance
- **WHEN** test code calls `container.register(MyClass)`
- **THEN** `TypeError` is raised
- **AND** the message contains `"v0.38"` and names `"Container.provide"`

#### Scenario: legacy `resolve` raises with hint

- **WHEN** test code calls `container.resolve(MyClass)`
- **THEN** `TypeError` is raised
- **AND** the message contains `"v0.38"` and names `"await Container.get"`

#### Scenario: legacy `has` raises with hint

- **WHEN** test code calls `container.has(MyClass)`
- **THEN** `TypeError` is raised
- **AND** the message contains `"v0.38"` and names `"Container.has_provider"`

### Requirement: Container exposes the v0.36+ resolution surface

The `Container` class SHALL provide this resolution + registration surface as the only callable path for new code:

- `provide(type_, factory, *, scope=Scope.SINGLETON)`
- `has_provider(type_)`
- `providers_view()`
- async `get(type_)`
- async `resolve_params(fn)`
- async `dispatch(fn, wire_kwargs, *, pre_hook=None)` (async context manager)
- `child()`
- async `aclose()`
- async `__aenter__` / `__aexit__`

The legacy method names (`register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, `has_any_async_singletons`) remain as attribute stubs that raise `TypeError` with migration hints (per the "Legacy DI methods raise `TypeError`" requirement). The wire-scope helpers (`register_wire_scope`, `wire_scopes`, `wire_scopes_used_by`) remain — they are wire-side plumbing, not DI resolution. The test-only `_override` / `_snapshot` / `_restore` seam (underscore-prefixed) remains.

#### Scenario: new surface is callable

- **GIVEN** a fresh `Container` instance
- **WHEN** new-surface methods are called against a registered type
- **THEN** `provide`, `has_provider`, `providers_view`, `get`, `resolve_params`, `dispatch`, `child`, `aclose` complete without raising `TypeError`
