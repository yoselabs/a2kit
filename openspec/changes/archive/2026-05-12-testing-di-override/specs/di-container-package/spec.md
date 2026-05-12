## ADDED Requirements

### Requirement: Container exposes a sealed test-only snapshot/restore pair

The `Container` class SHALL provide two methods, `_snapshot()` and `_restore(snapshot)`, used exclusively by `a2kit.packages.testing` to implement scoped test overrides. The methods SHALL:

- be synchronous,
- be feature-agnostic (no references to specific feature names),
- be prefixed with a single underscore to signal "test-only, not part of the documented public surface",
- preserve the rest of the documented public surface unchanged (`register`, `has`, `providers`, `resolve`, `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`).

`_snapshot()` SHALL return an opaque value capturing the current `_providers` and `_singletons` state (shallow copies). `_restore(snapshot)` SHALL replace those two structures with the snapshot's contents, discarding any intervening mutations.

The hot-path `resolve` method SHALL NOT branch on test-only state; snapshot/restore SHALL achieve override semantics by mutating the existing provider and singleton dicts, not by introducing a separate override layer consulted on every resolve.

#### Scenario: Snapshot captures provider and singleton state

- **GIVEN** a Container with `register(A, fa)` and `register_singleton(B, fb)` applied
- **WHEN** test code calls `snap = container._snapshot()` and then mutates the container by calling `register(A, fa2)` and assigning into `_singletons`
- **THEN** calling `container._restore(snap)` returns `_providers` and `_singletons` to the exact state captured by `snap`

#### Scenario: Snapshot/restore is feature-agnostic

- **WHEN** the source of `_snapshot` / `_restore` is read
- **THEN** the code contains no reference to feature names (`"connection"`, `"tracker"`, etc.) — only the generic two-dict capture/replace

#### Scenario: Resolve hot path is untouched

- **WHEN** the `Container.resolve` method body is read after this change
- **THEN** it contains no branch that consults a `_overrides` map or other test-only side state; override semantics are implemented entirely by mutating `_providers` and `_singletons` through the snapshot pair
