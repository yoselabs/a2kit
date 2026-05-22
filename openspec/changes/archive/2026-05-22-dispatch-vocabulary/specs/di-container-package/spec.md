## MODIFIED Requirements

### Requirement: Public surface is small and synchronous

The container's public surface SHALL consist of:

- **`Container` class** with the resolution and registration surface used by new code: `provide(t, factory, *, scope: Scope = Scope.SINGLETON)`, `has_provider(t) -> bool`, `providers()` (or `providers_view()`), `resolve(t)` (sync hot path), async `get(t)` (the canonical async path that may run `__aenter__` / await factories), `resolve_params(fn)`, `call_scope(fn, wire_kwargs, *, pre_hook=None)`, `child() -> Container`, async `aclose()`, plus the async context manager protocol (`__aenter__` / `__aexit__`). The method `call_scope` is the per-call DI scope: an async context manager that opens a per-call child container, runs the optional `pre_hook`, resolves DI kwargs, yields the merged kwargs, and unwinds the child on exit. The legacy method name `register` is not part of this surface — it was retired; see `request-scoped-di` for the legacy-name handling. The legacy method name `dispatch` is not part of this surface — it was renamed to `call_scope`; no alias is provided.

- **`Scope` enum** with values `SINGLETON`, `SCOPED`, `TRANSIENT`.
- **`Resolver` Protocol** declaring the narrow surface a2kit framework modules use.
- **`UnresolvableType` exception**.

Sync `Container.resolve(t)` SHALL remain for the hot path within a scope but SHALL raise `ValueError` if asked to resolve an async-factory app-scope type whose factory has not yet been awaited.

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
