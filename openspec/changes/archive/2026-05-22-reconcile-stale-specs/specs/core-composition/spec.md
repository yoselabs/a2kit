## MODIFIED Requirements

### Requirement: A2K-CORE-PURITY lint rule is removed

The `A2K-CORE-PURITY` lint rule SHALL NOT exist. `src/a2kit/packages/lint/rules/core_purity.py` MUST NOT be present. The rule constant MUST NOT appear in `src/a2kit/packages/lint/static.py::ALL_RULES`. Tests for the rule MUST NOT be present in the test tree. This is consistent with the `core-purity` capability, whose `A2K-CORE-CLEAN`-dependent requirement is removed in the same reconciliation: no core-purity-token lint rule of any name (`A2K-CORE-PURITY`, `A2K-CORE-CLEAN`) is part of the live rule set. Core import discipline is policed structurally by `A2K-LAYER` (see `import-acyclicity` and `module-layout-discipline`).

#### Scenario: Lint rule constant is gone

- **WHEN** user runs `uv run a2kit lint static src/`
- **THEN** the output never references `A2K-CORE-PURITY` or `A2K-CORE-CLEAN`

#### Scenario: Core may import from packages

- **WHEN** a core file imports a package symbol at module level where doing so is structurally appropriate
- **THEN** no core-purity-token lint rule fires; layering is policed by `A2K-LAYER`, not by a token blocklist
