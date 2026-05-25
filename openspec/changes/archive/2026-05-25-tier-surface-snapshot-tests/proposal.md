## Why

ADR 0004 enumerates Tier 1 names (the 95% verb-authoring surface) and
states that adding `_LAZY_ATTRS` entries requires an ADR. The coherence
audit (2026-05-25) found `Principal` promoted to Tier 1 without an ADR
— the slip happened because there is no enforcement step between
"edit `_LAZY_ATTRS`" and "ADR 0004 review". Convention failed.

Mature Python frameworks (attrs, Pydantic) solve this with a public-API
snapshot test: a checked-in expectation of `dir(<tier>)`; adding a
symbol forces a visible diff that gates review. This change adds the
same mechanism to a2kit.

## What Changes

- Add one pytest module that snapshots the public surface of each tier
  against a checked-in expectation file:
  - Tier 1: `dir(a2kit)` (filtered for public names)
  - Tier 2: `dir(a2kit.testing)`, `dir(a2kit.ldd)`, `dir(a2kit.schema)`,
    and any other `a2kit.<domain>` module that exists.
  - Plus an inventory of `_LAZY_ATTRS` keys in `src/a2kit/__init__.py`.
- Checked-in expectations live under
  `tests/surface/expected_tier1.txt`, `expected_tier_testing.txt`, etc.
  Tooling: plain sorted text files (no JSON noise; one symbol per line).
- A pytest fails when observed dir does not match expected; the
  failure message names the added/removed symbols and the path to the
  expected file.
- A small `make` target or test marker regenerates expectations:
  `make surface-snapshot` (or
  `pytest tests/surface --regen-snapshots`).
- **Decision-forcing**: the Principal Tier-1 promotion question resolves
  as a side-effect — either the snapshot is updated and an ADR filed,
  or `Principal` is demoted out of Tier 1. The test forces one of those
  to happen.

## Capabilities

### New Capabilities

- `public-api-tier-snapshot`: testable expectation files for each
  public tier; pytest enforces drift; regeneration command documented.

### Modified Capabilities

- `thin-core-surface`: gains a requirement that Tier 1 / Tier 2
  surfaces are snapshot-tested and that any symbol addition is a
  reviewable diff.

## Impact

- Affected code: `src/a2kit/__init__.py` (unchanged behaviour;
  `_LAZY_ATTRS` becomes the source of truth for the snapshot).
  Resolves the open Principal Tier-1 question.
- Tests: new `tests/surface/` directory.
- Build: optional `Makefile` target for regeneration.
- Dependencies: none.
- Documentation: ADR 0004 referenced in the failure message; an
  ADR for Principal (or a demote PR) follows this change.
