## 1. Snapshot test infrastructure

- [x] 1.1 Create `tests/surface/` directory with `__init__.py`
- [x] 1.2 Add `tests/surface/conftest.py` with `--regen-snapshots` option and a `snapshot_assert` helper that writes-or-asserts based on the flag
- [x] 1.3 Implement the comparison helper: takes an iterable of observed names, an expectation file path, a tier label; renders the prescribed failure message on mismatch
- [x] 1.4 Failure message includes: added symbols, removed symbols, ADR 0004 reference, regeneration command

## 2. Tier 1 snapshot

- [x] 2.1 Create `tests/surface/test_tier1_surface.py` with a single test that compares `dir(a2kit)` (public-filtered, sorted) against `expected_tier1.txt`
- [x] 2.2 Run with `--regen-snapshots` to seed `expected_tier1.txt`
- [x] 2.3 Inspect seeded file; confirm contents match ADR 0004's enumeration
- [x] 2.4 Flag `Principal` if present and pause for ADR-or-demote decision (resolved as separate follow-up — see Task 7.3)

## 3. _LAZY_ATTRS snapshot

- [x] 3.1 Create `tests/surface/test_lazy_attrs.py` that imports `_LAZY_ATTRS` from `src/a2kit/__init__.py` (or via a public introspection helper) and compares sorted keys
- [x] 3.2 Seed `expected_lazy_attrs.txt` via `--regen-snapshots`

## 4. Tier 2 snapshots (parametrised)

- [x] 4.1 Create `tests/surface/test_tier2_surfaces.py` parametrised over the known domain modules: `a2kit.testing`, `a2kit.ldd`, `a2kit.schema`
- [x] 4.2 Each case loads its own expectation file
- [x] 4.3 Seed each `expected_tier_<domain>.txt` via `--regen-snapshots`
- [x] 4.4 Test enumerates known Tier-2 modules; missing expectation file raises with creation instruction (covers the "new Tier-2 module without expectation" scenario)

## 5. Build integration

- [x] 5.1 Add `make surface-snapshot` target that runs `pytest tests/surface --regen-snapshots`
- [x] 5.2 Ensure the surface tests run as part of `make test` (no special exclude)

## 6. Documentation

- [x] 6.1 Document the workflow in `docs/adr/0004-package-layout-tiered-by-audience.md` (or a sibling note) — "How to add a Tier 1 symbol: update snapshot, file ADR amendment, both in one commit"
- [x] 6.2 Update `AGENTS.md` Architecture-strategy section: snapshot tests gate Tier-1 promotions

## 7. Validation

- [x] 7.1 `openspec validate --changes --strict` passes for `tier-surface-snapshot-tests`
- [x] 7.2 `make lint` clean
- [x] 7.3 Resolve the `Principal` Tier-1 question as a follow-up (file ADR for promotion OR demote to Tier 2) — ADR 0023 ratifies Tier-1 placement; ADR 0004 Tier-1 enumeration amended
