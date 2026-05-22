# module-layout-discipline Specification

## MODIFIED Requirements

### Requirement: A2K010 (legacy `--select` atom rule) is retired

The A2K010 rule and all its supporting code paths SHALL be removed from `a2kit.packages.lint`. The rule code and its disable list entries SHALL not appear in `pyproject.toml [tool.a2kit.lint]`.

#### Scenario: A2K010 not in ALL_RULES
- **WHEN** `a2kit.packages.lint.static.ALL_RULES` is inspected
- **THEN** the tuple does not contain `"A2K010"`

#### Scenario: No `_parse_select_atoms_cel` stub
- **WHEN** `grep -rE "_parse_select_atoms_cel|A2K010" src/a2kit/packages/lint/` is run
- **THEN** the result is empty
