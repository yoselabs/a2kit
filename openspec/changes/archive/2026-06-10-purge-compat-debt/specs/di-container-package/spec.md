# di-container-package

## MODIFIED Requirements

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

Async `Container.get(t)` is the single resolution path; there is no
sync resolution method.

#### Scenario: `seed_scoped` appears in the package's exported surface

- **WHEN** inspecting `a2kit.packages.di.Container`'s public methods
  (those without leading underscore)
- **THEN** `seed_scoped` is among them
- **AND** its docstring documents the child-only constraint

#### Scenario: Async `get` is the canonical resolution path

- **WHEN** `inspect.iscoroutinefunction(Container.get)` is checked
- **THEN** the result is `True`
- **AND** `Container.get(T)` may invoke `__aenter__` on the resolved instance and record cleanup on the scope's cleanup stack

#### Scenario: `Scope` enum has the three documented values

- **WHEN** `list(Scope)` is enumerated
- **THEN** the result is `[Scope.SINGLETON, Scope.SCOPED, Scope.TRANSIENT]` (or equivalent ordering)
- **AND** `Scope.__module__` is `"a2kit.packages.di"`

#### Scenario: `register` is not a callable resolution method

- **WHEN** `Container.register` is accessed
- **THEN** it raises `AttributeError` (the name is removed, per `request-scoped-di`) — it is not the registration path; `provide` is

#### Scenario: `dispatch` is not a callable method

- **WHEN** `Container.dispatch` is accessed
- **THEN** it does not resolve to the per-call scope helper — the method was renamed to `call_scope` and no alias is kept
