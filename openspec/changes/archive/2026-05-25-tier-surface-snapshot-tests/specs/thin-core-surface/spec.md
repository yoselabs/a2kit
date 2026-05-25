## ADDED Requirements

### Requirement: Public-tier surface drift is gated by snapshot tests

The library SHALL enforce ADR 0004's tier discipline with snapshot
tests for Tier 1 (`a2kit.*`) and every Tier 2 (`a2kit.<domain>`) module.
A change to the set of public names exposed by any tier MUST appear as
a diff in the corresponding `tests/surface/expected_tier*.txt` file
and MUST be reviewed alongside any ADR amendment that justifies the
change.

#### Scenario: Adding a Tier-1 symbol requires a paired expectation diff

- **WHEN** a developer adds a name to `_LAZY_ATTRS` in
  `src/a2kit/__init__.py`
- **AND** does not update `tests/surface/expected_tier1.txt` or
  `expected_lazy_attrs.txt`
- **THEN** `make test` fails
- **AND** the failure message names the added symbol and references
  ADR 0004

#### Scenario: Demoting a symbol requires the same diff

- **WHEN** a developer moves a symbol from Tier 1 to a Tier-2 module
- **THEN** the Tier-1 expectation removes the name
- **AND** the Tier-2 expectation adds the name
- **AND** both diffs appear in the commit
