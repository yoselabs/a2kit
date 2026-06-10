# request-scoped-di

## REMOVED Requirements

### Requirement: Legacy DI methods raise `TypeError` with migration hints

**Reason**: The retired-name stubs and their embedded migration hints are
removed (no backward compatibility, no migration hints). The old names no
longer exist on `Container`; accessing one raises the language-default
`AttributeError`. The migration recipe lives only in the CHANGELOG. Replaced
by "Legacy DI method names are removed".

## ADDED Requirements

### Requirement: Legacy DI method names are removed

The legacy DI method names SHALL be removed from `Container`: `register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, and `has_any_async_singletons`. The names SHALL NOT resolve to any attribute; accessing one raises the language-default `AttributeError` with no embedded migration hint and no alias. The replacements (`provide`, `get`, `has_provider`) are documented in the CHANGELOG.

#### Scenario: legacy `register` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.register`
- **THEN** `AttributeError` is raised

#### Scenario: legacy `resolve` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.resolve`
- **THEN** `AttributeError` is raised

#### Scenario: legacy `has` is gone

- **GIVEN** a `Container` instance
- **WHEN** test code accesses `container.has`
- **THEN** `AttributeError` is raised

## MODIFIED Requirements

### Requirement: Container exposes the v0.36+ resolution surface

The `Container` class SHALL provide this resolution + registration surface as the only callable path for new code:

- `provide(type_, factory, *, scope=Scope.SINGLETON)`
- `has_provider(type_)`
- `providers_view()`
- async `get(type_)`
- async `resolve_params(fn)`
- async `call_scope(fn, wire_kwargs, *, pre_hook=None)` (async context manager)
- `child()`
- async `aclose()`
- async `__aenter__` / `__aexit__`

The legacy method names (`register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, `has_any_async_singletons`) are removed — they do not resolve to any attribute and accessing one raises `AttributeError`. The test-only `_override` / `_snapshot` / `_restore` seam does NOT exist — it was deleted. Test-time dependency swaps are done by composition-root re-registration (constructing a fresh `App` and calling `provide` with the fake), not by mutating a sealed container.

#### Scenario: new surface is callable

- **GIVEN** a fresh `Container` instance
- **WHEN** new-surface methods are called against a registered type
- **THEN** `provide`, `has_provider`, `providers_view`, `get`, `resolve_params`, `call_scope`, `child`, `aclose` complete without raising `TypeError`

#### Scenario: no test-override seam exists

- **WHEN** `packages/di/container.py` is inspected for `_override`, `_snapshot`, `_restore`
- **THEN** no such member is defined on `Container`
