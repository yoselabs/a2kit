## ADDED Requirements

### Requirement: Spec-drift gate scans every capability spec

The repository SHALL include a test (`tests/test_spec_symbol_drift.py`) that scans every `openspec/specs/*/spec.md` file and asserts every checkable code-font symbol resolves on the live `a2kit` surface in `src/a2kit/`.

The test is the spec-tree sibling of `tests/test_readme_symbol_drift.py`: it imports `a2kit`, extracts backtick-quoted (code-font) spans from each spec file, and resolves each checkable symbol by binding against live types — not by text-matching `src/`. Every file matching `openspec/specs/*/spec.md` SHALL be in scope; no capability spec is exempt.

#### Scenario: All spec symbols resolve

- **WHEN** every capability spec under `openspec/specs/` cites only symbols that exist on the live `a2kit` surface
- **THEN** `pytest tests/test_spec_symbol_drift.py` passes

#### Scenario: Every spec file is scanned

- **WHEN** a new `openspec/specs/<cap>/spec.md` file is added
- **THEN** the gate scans it on the next run with no per-file registration

### Requirement: Every checkable symbol must resolve

A checkable symbol cited in a code-font span of any capability spec MUST resolve in `src/a2kit/`, or the gate MUST fail.

A symbol is checkable when, inside a backtick-quoted span, it matches one of: a dotted a2kit path (`a2kit.X` or `a2kit.<submod>.Y`, optionally `@`-prefixed); an attribute access on a canonical type (`App.x`, `app.x`, `Router.x`, `@app.x`, `Container.x`); or an a2kit lint-rule code (the `A2K-` prefixed form). Bare lowercase words, string literals, file paths, shell commands, type-annotation fragments, and tokens under a known non-a2kit prefix are NOT checkable and SHALL be skipped. Dotted paths and canonical-type accesses resolve via `hasattr` / `importlib`; lint-rule codes resolve against the live a2kit lint-rule registry.

#### Scenario: Stale dotted symbol is caught

- **WHEN** a capability spec cites `` `a2kit.Param` `` in a code-font span and `a2kit` has no `Param` attribute
- **THEN** the gate fails, naming the symbol, the spec file, and the line

#### Scenario: Stale canonical-type access is caught

- **WHEN** a capability spec cites `` `Container._snapshot` `` and `Container` has no `_snapshot` attribute
- **THEN** the gate fails, naming the symbol, the spec file, and the line

#### Scenario: Stale lint-rule code is caught

- **WHEN** a capability spec cites `` `A2K-DI-CHAIN` `` and no such rule exists in the live lint-rule registry
- **THEN** the gate fails, naming the rule code, the spec file, and the line

#### Scenario: Illustrative token is not checked

- **WHEN** a capability spec cites a type-annotation fragment such as `` `Lazy[T]` `` or a third-party token such as `` `pydantic.Field` ``
- **THEN** the gate treats it as not checkable and does not fail on it

### Requirement: An allowlist exempts legitimately-illustrative identifiers

The gate MUST carry an explicit allowlist for structurally-a2kit-shaped symbols that legitimately do not resolve.

The allowlist is a single constant co-located with the gate, covering example-only placeholder names (e.g. `TrackerStore`, `ProjectsRouter`), tombstone migration targets a spec cites to document a removed name, and grandfathered known-drift symbols entered when the gate is first landed. Every allowlist entry SHALL carry a comment naming why it is exempt; grandfathered-drift entries SHALL carry a `# reconcile:` tag so `reconcile-stale-specs` can find and remove them. A symbol in the allowlist SHALL NOT cause the gate to fail even if it does not resolve.

#### Scenario: Example-only name is allowlisted

- **WHEN** a capability spec cites `` `TrackerStore` `` as an illustrative placeholder and that name is in the allowlist
- **THEN** the gate does not fail on it

#### Scenario: Tombstone migration target is allowlisted

- **WHEN** a capability spec's REMOVED-requirement migration text cites a removed name such as `` `a2kit.AppBuilder` `` and that name is in the allowlist
- **THEN** the gate does not fail on the deliberately-removed name

#### Scenario: Grandfathered drift is tagged for reconciliation

- **WHEN** the gate is first landed and today's already-drifted symbols are added to the allowlist
- **THEN** each such entry carries a `# reconcile:` comment so the `reconcile-stale-specs` change can remove it after fixing the spec

### Requirement: The gate runs in CI and `make check`

The spec-drift gate SHALL run as part of `make lint`, and therefore as part of `make check` and CI, so spec drift fails at PR time rather than at reader-trust time.

The gate is added to `make lint` as a dedicated `pytest tests/test_spec_symbol_drift.py` invocation, immediately after the existing README symbol-drift gate line, mirroring its treatment. Because `make check` runs `make lint`, and CI and the pre-commit hook run the same targets, the gate needs no separate wiring.

#### Scenario: Gate runs under make lint

- **WHEN** a contributor runs `make lint`
- **THEN** the spec-drift gate executes and any drift fails the lint target

#### Scenario: Gate runs under make check

- **WHEN** a contributor runs `make check`
- **THEN** the spec-drift gate executes as part of the `lint` dependency

### Requirement: Gate failure output is a reconciliation worklist

The gate MUST emit, on failure, one line per unresolved symbol naming the spec file, the line number, the symbol, and the reason it did not resolve.

The failure format mirrors the README gate's `README.md:<line> — <sym>: <reason>` shape, producing `openspec/specs/<cap>/spec.md:<line> — <symbol>: <reason>`. This output is the worklist the separate `reconcile-stale-specs` change consumes: `add-spec-drift-gate` is applied first and the gate's failure list drives the reconciliation work.

#### Scenario: Failure names file, line, symbol, and reason

- **WHEN** the gate finds an unresolved symbol in a capability spec
- **THEN** the failure message includes the spec file path, the line number, the symbol, and the attempted resolution that failed

#### Scenario: Output drives the reconcile change

- **WHEN** `reconcile-stale-specs` begins
- **THEN** the spec-drift gate's failure list is usable directly as that change's worklist of stale specs to fix
