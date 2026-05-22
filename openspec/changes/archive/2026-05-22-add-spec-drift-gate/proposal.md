## Why

a2kit moved through ~7 minors fast. Three artifact layers must stay in
sync — CODE (`src/`), SPECS (`openspec/specs/`), and DOCS. Code is
exercised every commit (test + lint + ty), so it stays fresh. DOCS have
a gate: `tests/test_readme_symbol_drift.py` checks every README symbol
resolves on the live surface. SPECS have nothing. An OpenSpec capability
spec is only re-touched when a change explicitly deltas that capability,
so any capability nobody changed in 10 versions silently rots. An audit
found ~18 of 36 specs drifted or stale, asserting symbols that no longer
exist in code (`a2kit.Param`, `Container._snapshot` / `_restore` /
`_override`, `App.singleton`, `@app.on_startup`, lint rules
`A2K-DI-CHAIN` / `A2K-DI-PROVIDER`). There is no mechanical SPEC↔code
check, so the rot is invisible until a reader trusts a dead spec.

A second, related problem: "tombstones" (loud-crash-with-hint code for
removed APIs, per AGENTS.md doctrine) have a defined birth — name the
surface, the replacement, and the version — but no defined death. They
accumulate (a v0.33 tombstone is still here at v0.40). When a
tombstone's delivery mechanism is itself removed, the tombstone dies
silently and its spec does not notice. Tombstone behavior is also
wrongly encoded as Requirements in *living* specs, which guarantees
drift — a living spec keeps asserting a removed-surface raise long after
the raise mechanism is gone.

This change closes the SPEC↔code hole and records the missing
tombstone-lifecycle doctrine so the rot stops re-accumulating.

## What Changes

- **A spec-drift gate.** A new test, sibling of
  `tests/test_readme_symbol_drift.py`, scans every
  `openspec/specs/*/spec.md`, extracts code-font (backtick-quoted)
  symbols that look like Python identifiers / dotted paths / a2kit
  lint-rule codes, and asserts each resolves in `src/a2kit/`. It cannot
  check prose ("SHALL raise with a hint") but it mechanically catches
  dead-symbol drift, which is most of the damage.
- **An explicit allowlist** for legitimately-illustrative identifiers
  (example-only names, generic placeholders, removed-on-purpose
  tombstone names cited as migration targets). The allowlist is the
  single tuning knob that keeps false positives low.
- **The gate joins the lint pipeline.** It runs under `make lint` /
  `make check` and in CI, exactly as the README gate does, so spec
  regressions fail at PR time, not at reader-trust time.
- **A tombstone-lifecycle ADR** (new `docs/adr/0018-*.md`, next free
  number) records the doctrine: tombstones are permanent but cheap
  (data-driven — one registry dict plus one `__getattr__` per module,
  not hand-written per-method raise-stubs); removed-surface behavior is
  NOT a living-spec Requirement (if specced at all it is a short-lived
  ADDED requirement in the removing change, REMOVED a couple minors
  later); and a superseded *capability* spec is DELETED from
  `openspec/specs/`, not left as an emptied husk of REMOVED
  requirements. The ADR file itself is written as a task in `tasks.md`,
  not in this proposal.

This change is the **worklist generator** for the separate
`reconcile-stale-specs` change: once the gate exists, its failure output
*is* the list of stale specs to reconcile. `add-spec-drift-gate` MUST be
applied before `reconcile-stale-specs` — the gate is intentionally
landed first with whatever allowlist is needed to go green against
today's (already-drifted) specs being grandfathered in, then
`reconcile-stale-specs` fixes the specs and shrinks the allowlist.

## Capabilities

### New Capabilities

- `spec-drift-gate`: a CI gate that scans every
  `openspec/specs/*/spec.md`, extracts backtick-quoted Python-identifier
  / dotted-path / a2kit-lint-rule symbols, and asserts each resolves in
  `src/a2kit/`; backed by an explicit allowlist for illustrative names;
  runs under `make lint` / `make check`.

### Modified Capabilities

<!-- none — docs-code-parity stays README-scoped; the spec gate is a
     distinct mechanical concern over a distinct artifact tree and earns
     its own capability (see design.md, Decision D1). -->

## Impact

- **Tests**: new `tests/test_spec_symbol_drift.py` (the gate). Sibling
  of `tests/test_readme_symbol_drift.py`; shares its resolution
  approach (bind against live `a2kit.*` types, not text-match).
- **Build**: `make lint` gains one `pytest` invocation for the new test,
  matching the existing README-gate line.
- **Decision log**: a new ADR (`docs/adr/0018-*.md`) recording
  tombstone lifecycle and the superseded-spec-deletion rule;
  `make adr-index` regenerates `docs/adr/INDEX.md`.
- **Specs**: one new capability spec, `spec-drift-gate`. No existing
  spec's requirements change in this change — drifted specs are
  reconciled by the follow-up `reconcile-stale-specs` change, which this
  gate's output drives.
- **Sequencing**: apply this change before `reconcile-stale-specs`.
