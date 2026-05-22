## MODIFIED Requirements

### Requirement: Per-call result caching

The container SHALL cache resolved instances within the lifetime of a single tool dispatch and SHALL NOT share instances across dispatches, except for types registered with app scope (`app.provide(T, ...)` with `per_call=False`, the default), whose cached instance is shared across all dispatches on the App.

#### Scenario: Same type resolved twice in one call

- **GIVEN** a tool method declares both `store: TrackerStore` and `audit: AuditLog` where `AuditLog`'s factory also depends on `TrackerStore`
- **WHEN** the tool is dispatched
- **THEN** the `TrackerStore` instance bound to `store` and the one passed to the `AuditLog` factory are the same object

#### Scenario: App-scope instance shared across calls

- **GIVEN** `app.provide(AppState, factory)` registered (default `per_call=False`)
- **WHEN** the same tool is dispatched twice
- **THEN** both dispatches receive the same `AppState` object

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

The legacy method names (`register`, `register_singleton`, `resolve`, `aresolve`, `has`, `has_async_singleton`, `has_any_async_singletons`) remain as attribute stubs that raise `TypeError` with migration hints. The test-only `_override` / `_snapshot` / `_restore` seam does NOT exist — it was deleted. Test-time dependency swaps are done by composition-root re-registration (constructing a fresh `App` and calling `provide` with the fake), not by mutating a sealed container.

#### Scenario: new surface is callable

- **GIVEN** a fresh `Container` instance
- **WHEN** new-surface methods are called against a registered type
- **THEN** `provide`, `has_provider`, `providers_view`, `get`, `resolve_params`, `dispatch`, `child`, `aclose` complete without raising `TypeError`

#### Scenario: no test-override seam exists

- **WHEN** `packages/di/container.py` is inspected for `_override`, `_snapshot`, `_restore`
- **THEN** no such member is defined on `Container`

## REMOVED Requirements

### Requirement: Connection-rooted resolution boundary

**Reason**: This requirement mandates a lint rule `A2K-DI-CHAIN` that enforces "only the auto-installed config provider may take a `connection: str` parameter." No `A2K-DI-CHAIN` rule exists in `a2kit.packages.lint`. A requirement whose normative content is "this lint rule SHALL enforce X" cannot stand when the rule was never built.

**Migration**: There is no `A2K-DI-CHAIN` rule. Connection-to-config transformation happens via the dispatch-hook seam (see the `connections-dispatch-hook` capability); the container itself does not special-case any parameter name.

### Requirement: Lint enforces provider availability

**Reason**: This requirement mandates a lint rule `A2K-DI-PROVIDER` that fails when a tool declares an injectable kwarg type with no registered provider. No `A2K-DI-PROVIDER` rule exists in `a2kit.packages.lint`. The requirement's scenarios (`A2K-DI-PROVIDER reports TrackerStore as missing`) cannot be satisfied.

**Migration**: There is no `A2K-DI-PROVIDER` rule. A missing provider surfaces at resolution time as `UnresolvableType` (see the "Container chains providers by parameter annotation" requirement), not as a static lint finding.
