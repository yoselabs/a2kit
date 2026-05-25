# public-api-tier-snapshot Specification

## Purpose
TBD - created by archiving change tier-surface-snapshot-tests. Update Purpose after archive.
## Requirements
### Requirement: Tier 1 public surface is snapshot-tested

A pytest module under `tests/surface/` SHALL compare the observed
public surface of the top-level `a2kit` module against a checked-in
expectation file. The observed surface is `sorted(n for n in dir(a2kit)
if not n.startswith("_"))`. The expectation file is
`tests/surface/expected_tier1.txt`, one name per line, sorted. On
mismatch, the test SHALL fail with a message naming the added/removed
symbols and pointing at ADR 0004.

#### Scenario: Surface matches expectation

- **GIVEN** `tests/surface/expected_tier1.txt` lists all current public
  names of `a2kit`
- **WHEN** the snapshot test runs
- **THEN** the test passes

#### Scenario: Adding a symbol fails the test

- **GIVEN** a developer adds a new entry to `_LAZY_ATTRS` in
  `src/a2kit/__init__.py` without updating the expectation file
- **WHEN** the snapshot test runs
- **THEN** the test fails
- **AND** the failure message lists the added symbol
- **AND** references ADR 0004 and the regeneration command

#### Scenario: Removing a symbol fails the test

- **GIVEN** a developer removes an entry from `_LAZY_ATTRS` without
  updating the expectation file
- **WHEN** the snapshot test runs
- **THEN** the test fails
- **AND** the failure message lists the removed symbol

### Requirement: Tier 2 public surfaces are snapshot-tested

The snapshot suite SHALL include one parametrised case per Tier-2 domain module (`a2kit.testing`, `a2kit.ldd`, `a2kit.schema`, and any future `a2kit.<domain>`). Each case MUST compare `dir(module)` filtered to public names against a per-module expectation file at `tests/surface/expected_tier_<domain>.txt` and fail on drift.

#### Scenario: a2kit.testing snapshot matches

- **GIVEN** `tests/surface/expected_tier_testing.txt`
- **WHEN** the snapshot test runs for `a2kit.testing`
- **THEN** observed public surface equals the expectation

#### Scenario: New Tier-2 module without expectation fails

- **GIVEN** a developer adds `src/a2kit/auth.py` as a Tier-2 module
  but does not add an expectation file
- **WHEN** the snapshot test runs
- **THEN** the test fails
- **AND** the failure message instructs creating the expectation file

### Requirement: _LAZY_ATTRS keys are independently snapshotted

The snapshot suite SHALL include a case that asserts
`sorted(_LAZY_ATTRS.keys())` from `src/a2kit/__init__.py` matches a
checked-in `tests/surface/expected_lazy_attrs.txt`. This catches
additions even before the lazy attribute has been resolved by any
consumer.

#### Scenario: _LAZY_ATTRS keys match snapshot

- **GIVEN** `expected_lazy_attrs.txt` lists the current `_LAZY_ATTRS` keys
- **WHEN** the snapshot test runs
- **THEN** observed keys equal expected keys

#### Scenario: Lazy attr addition is flagged

- **GIVEN** a new key in `_LAZY_ATTRS` not present in the expectation
- **WHEN** the test runs
- **THEN** the test fails with the added key named in the message

### Requirement: Regeneration is one command

The snapshot suite SHALL support a regeneration mode invoked by
`pytest tests/surface --regen-snapshots`. In this mode, mismatches
SHALL NOT raise; instead, the observed values overwrite the
expectation files. A subsequent normal run (without the flag) SHALL
pass.

#### Scenario: Regeneration overwrites expectations

- **GIVEN** the surface has drifted from the expectation file
- **WHEN** the developer runs `pytest tests/surface --regen-snapshots`
- **THEN** the expectation files are rewritten to match observation
- **AND** the test suite reports the regeneration in stdout
- **AND** a follow-up `pytest tests/surface` passes

