## Context

a2kit ships a 3-tier public surface (ADR 0004). The slip that exposed
the missing enforcement: `Principal` was added to `_LAZY_ATTRS` without
an ADR. The lint layer doesn't see this because `_LAZY_ATTRS` is a dict
literal, not an import.

Mature Python frameworks treat the public surface as a contract and
test it. attrs and Pydantic both have public-API snapshot tests; both
catch accidental promotions before release.

## Goals / Non-Goals

**Goals:**
- Make every public-surface change a visible diff against a checked-in
  expectation file.
- Cover Tier 1 (`a2kit.*`) and Tier 2 (`a2kit.<domain>` modules).
- Provide a one-command regeneration path so the workflow is
  "snapshot diff → review → update expectation + ADR if needed".
- Cheap: pure-Python pytest, no new dependencies.

**Non-Goals:**
- Snapshotting Tier 3 (`a2kit.packages.*`). Those are implementation
  paths; their stability contract is different.
- Snapshotting method signatures or annotations. The contract is
  "what names exist"; deeper API shape testing is out of scope.
- Replacing the layer DAG lint. This is a complementary check, not a
  substitute.

## Decisions

### 1. Plain-text expectation files, one symbol per line, sorted

Format: `tests/surface/expected_tier1.txt` is a sorted newline-
separated list of public names. Diffs read naturally; merge conflicts
resolve trivially.

Alternative considered: JSON / YAML. Rejected — line-oriented diffs and
review-friendly merges win.

### 2. Filter rule: a "public name" is one not starting with `_`

Public surface = `[n for n in dir(module) if not n.startswith("_")]`.
This catches both eager exports and lazy `__getattr__` exposures.

Alternative considered: introspect `__all__`. Rejected — `__all__` is
not always complete or always defined; `dir()` reflects reality
including the lazy attrs.

### 3. Snapshot includes `_LAZY_ATTRS` keys explicitly

A second snapshot file `expected_lazy_attrs.txt` enumerates the keys of
`src/a2kit/__init__.py::_LAZY_ATTRS`. This catches additions even
before the symbol has been resolved by anyone.

Rationale: the Principal slip happened at the `_LAZY_ATTRS` literal;
mirroring it as a snapshot makes review surface-level.

### 4. Regeneration via pytest flag, not a separate script

`pytest tests/surface --regen-snapshots` rewrites the expectation files.
Implementation: a `conftest.py` fixture / option that, when set,
catches the assertion mismatch and writes the observed value instead of
raising.

Alternative considered: a separate `scripts/regen_surface.py`. Rejected
— pytest already loads the modules in the right environment; a script
re-implements that.

### 5. Failure message includes ADR 0004 reference and the changed file

When the snapshot fails:
```
Public surface of `a2kit` drifted.
  ADDED:    Principal
  REMOVED:  (none)
If this addition is intentional:
  - Update tests/surface/expected_tier1.txt
  - File or amend ADR 0004 to justify the promotion
Regenerate with: pytest tests/surface --regen-snapshots
```

### 6. No CI gating beyond the existing `make test`

The test runs as part of the regular suite. No special CI step. The
failure message tells the reader what to do.

## Risks / Trade-offs

- **[Risk] Snapshot tests are flaky if module loading is conditional**
  → Mitigation: the tier modules are deterministic on a fresh import;
  test runs in a clean process via pytest collection. If a name becomes
  conditional in the future, the test catches that too (regression).
- **[Risk] Reviewers ignore the snapshot diff and rubber-stamp**
  → Mitigation: the failure message and ADR 0004 update become a
  paired commit; the doctrine (audit, ADRs) is the cultural enforcement.
- **[Trade-off] Adding a public symbol is now a 2-line commit instead
  of 1** → Accepted: that's the point.

## Migration Plan

1. Land the snapshot test infra (tests/surface/, conftest, makefile
   target) with empty expectation files.
2. Run with `--regen-snapshots` to seed the current state.
3. Review the seeded expectations — `Principal` will be visible in
   `expected_lazy_attrs.txt`. Decide: file ADR or demote.
4. Commit final expectations.
5. Subsequent surface changes go through the snapshot-update + ADR
   review path.

No rollback complexity; the change is additive.

## Open Questions

- Should we snapshot `a2kit.errors` (a2effect re-exports), if such a
  Tier-2 module gets promoted? Defer until the audience justifies it.
- Should the snapshot diff itself be diff'd by a pre-commit hook to
  fail earlier than pytest? Defer; pytest is sufficient for now.
