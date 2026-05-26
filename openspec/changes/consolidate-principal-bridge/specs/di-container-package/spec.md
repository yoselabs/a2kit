## ADDED Requirements

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

#### Scenario: `seed_scoped` appears in the package's exported surface

- **WHEN** inspecting `a2kit.packages.di.Container`'s public methods
  (those without leading underscore)
- **THEN** `seed_scoped` is among them
- **AND** its docstring documents the child-only constraint

## REMOVED Requirements

### Requirement: `Container.call_scope` implicitly seeds typed instances from wire kwargs

**Reason**: The implicit `for _wire_val in wire.values(): type(_wire_val)` loop
that registers SCOPED providers based on dict iteration is invisible
at call sites — `wire_kwargs.setdefault("foo", value)` was effectively
a DI registration. The implicit seeding caused magic-string keys
(`"_a2kit_principal"`), undefined subclass semantics, and silent
type collisions for unrelated wire values.

**Migration**: callers that relied on the implicit walk MUST now seed
explicitly via `Container.seed_scoped(type_, value)` on the child
container. For `pre_hook` consumers, the hook signature widens to
receive a `seed: SeedFn` callable as the third argument. See the
`di-per-call-scope` spec delta for the new pre_hook contract.
