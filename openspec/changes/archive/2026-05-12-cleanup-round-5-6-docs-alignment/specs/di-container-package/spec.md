## MODIFIED Requirements

### Requirement: Container exposes a sealed test-only snapshot/restore pair

The `Container` class SHALL provide two methods, `_snapshot()` and `_restore(snapshot)`, used exclusively by `a2kit.packages.testing` to implement scoped test overrides. The methods SHALL:

- be synchronous,
- be feature-agnostic (no references to specific feature names),
- be prefixed with a single underscore to signal "test-only, not part of the documented public surface",
- preserve the rest of the documented public surface unchanged (`register`, `has`, `providers`, `resolve`, `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`).

`_snapshot()` SHALL return an opaque value capturing the current
`_providers`, `_singletons`, AND `_async_factories` state (shallow copies
of each of the three attributes). `_restore(snapshot)` SHALL replace
those three structures with the snapshot's contents, discarding any
intervening mutations. The third attribute (`_async_factories`) is
required because the container interacts with the
`singleton-async-factories` capability: an override that replaces an
async-registered singleton's factory would otherwise leave a stale
entry in `_async_factories`, causing the next sync resolve to raise
"async factory" against the restored state.

The hot-path `resolve` method SHALL NOT branch on test-only state; snapshot/restore SHALL achieve override semantics by mutating the existing provider, singleton, and async-factory dicts, not by introducing a separate override layer consulted on every resolve.

#### Scenario: Snapshot captures provider, singleton, and async-factory state

- **GIVEN** a Container with `register(A, fa)`, `register_singleton(B, fb)`, and `register_singleton(C, async_fc)` applied
- **WHEN** test code calls `snap = container._snapshot()` and then mutates the container by calling `register(A, fa2)`, assigning into `_singletons`, and replacing the entry in `_async_factories` for `C`
- **THEN** calling `container._restore(snap)` returns `_providers`, `_singletons`, AND `_async_factories` to the exact state captured by `snap`

#### Scenario: Snapshot/restore is feature-agnostic

- **WHEN** the source of `_snapshot` / `_restore` is read
- **THEN** the code contains no reference to feature names (`"connection"`, `"tracker"`, etc.) — only the generic three-dict capture/replace

#### Scenario: Resolve hot path is untouched

- **WHEN** the `Container.resolve` method body is read after this change
- **THEN** it contains no branch that consults a `_overrides` map or other test-only side state; override semantics are implemented entirely by mutating `_providers`, `_singletons`, and `_async_factories` through the snapshot pair
