## MODIFIED Requirements

### Requirement: Container exposes a sealed test-only snapshot/restore pair

The `Container` class SHALL provide three methods, `_snapshot()`, `_restore(snapshot)`, and `_override(type_, instance)`, used exclusively by `a2kit.packages.testing` to implement scoped test overrides. The methods SHALL:

- be synchronous,
- be feature-agnostic (no references to specific feature names),
- be prefixed with a single underscore to signal "test-only, not part of the documented public surface",
- preserve the rest of the documented public surface unchanged (`register`, `has`, `providers`, `resolve`, `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`).

`_snapshot()` SHALL return an opaque value capturing the current `_providers`, `_singletons`, and `_async_factories` state (shallow copies). `_restore(snapshot)` SHALL replace those three structures with the snapshot's contents, discarding any intervening mutations.

`_override(type_, instance)` SHALL replace the binding for `type_` with a constant pointing to `instance`. The method SHALL:

1. Set `_providers[type_]` to a zero-arg factory that returns `instance` (constant factory).
2. Set `_singletons[type_]` to `instance`.
3. Call `_async_factories.discard(type_)` to clear any async-factory marker that would otherwise block synchronous `resolve` of `type_`.

`_override` SHALL be the only sanctioned mutation path for the three-attribute swap used by `TestClient.override`. Callers SHALL NOT reach into `_providers`, `_singletons`, or `_async_factories` directly — those three attributes are now exclusively mutated through `_override` (for swap) and `_restore` (for revert).

The hot-path `resolve` method SHALL NOT branch on test-only state; snapshot/restore/override SHALL achieve override semantics by mutating the existing provider, singleton, and async-factory structures, not by introducing a separate override layer consulted on every resolve.

#### Scenario: Snapshot captures provider, singleton, and async-factory state

- **GIVEN** a Container with `register(A, fa)`, `register_singleton(B, fb)`, and an async-factory marker for `C` applied
- **WHEN** test code calls `snap = container._snapshot()` and then mutates the container by calling `register(A, fa2)`, assigning into `_singletons`, and discarding `C` from `_async_factories`
- **THEN** calling `container._restore(snap)` returns `_providers`, `_singletons`, and `_async_factories` to the exact state captured by `snap`

#### Scenario: Snapshot/restore is feature-agnostic

- **WHEN** the source of `_snapshot` / `_restore` / `_override` is read
- **THEN** the code contains no reference to feature names (`"connection"`, `"tracker"`, etc.) — only the generic three-attribute capture/replace/swap

#### Scenario: Resolve hot path is untouched

- **WHEN** the `Container.resolve` method body is read after this change
- **THEN** it contains no branch that consults a `_overrides` map or other test-only side state; override semantics are implemented entirely by mutating `_providers`, `_singletons`, and `_async_factories` through the snapshot / override / restore pair

#### Scenario: _override pins a singleton-registered binding

- **GIVEN** a Container with `register_singleton(LLMExtractor, lambda: RealLLM())` applied
- **WHEN** test code calls `container._override(LLMExtractor, FakeLLM())` and then `container.resolve(LLMExtractor)`
- **THEN** the resolved instance is the `FakeLLM` passed to `_override`

#### Scenario: _override pins a per-call provider-registered binding

- **GIVEN** a Container with `register(Store, build_store)` applied
- **WHEN** test code calls `container._override(Store, fake_store)` and then `container.resolve(Store)` multiple times
- **THEN** every resolution returns the same `fake_store` instance

#### Scenario: _override clears an async-factory marker

- **GIVEN** a Container where `type_` is registered with an async factory (marked in `_async_factories`)
- **WHEN** test code calls `container._override(type_, fake)` and then `container.resolve(type_)`
- **THEN** `resolve` returns `fake` synchronously and does not raise the "async factory blocks sync resolve" error
