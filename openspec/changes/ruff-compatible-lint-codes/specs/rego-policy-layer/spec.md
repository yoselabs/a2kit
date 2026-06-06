## MODIFIED Requirements

### Requirement: `noqa -- reason` suppression filters policy findings

Every Rego policy SHALL filter its `deny` set against the `suppressions` fact set before emission. A function carrying `# noqa: <RULE-ID> -- <reason text>` SHALL be excluded from findings of that rule ID. The grammar matches the project convention landed in commit `83819db` (`feat(lint): A2K-NO-DICT-STR-ANY + noqa --reason grammar`): the literal separator is ` -- ` (space-dash-dash-space) followed by free-text reason; no `--reason` keyword, no quotes required. Rule IDs are ruff-`noqa`-grammar-safe codes matching `^[A-Z]+[0-9]+$` under the reserved `RG` prefix (e.g. `RG001` for the former `REGO-BODY-DUP`, `RG002` for the former `REGO-NAME-COLLISION`); the legacy `REGO-*` spellings resolve to their `RG*` codes through `LEGACY_CODE_ALIASES` during the deprecation window. For `RG*` findings, a `# noqa: RG*` without a ` -- ` reason suffix SHALL be a hard structural error (stronger than the static `AK*` rules, where reasons are conventional). Rationale: Rego policies enforce architectural invariants; every suppression must be justified.

#### Scenario: noqa with reason suppresses the finding

- **GIVEN** a function carrying `# noqa: RG001 -- intentional parallel impl, see ADR-NNNN` AND a sibling function with matching `ast_hash_normalized`
- **WHEN** `body_dup.rego` runs
- **THEN** no `deny` is emitted for the suppressed function

#### Scenario: REGO noqa without reason is a hard error

- **GIVEN** a function carrying `# noqa: RG001` (no ` -- ` reason)
- **WHEN** `extract_facts.py` runs
- **THEN** the extractor exits non-zero and names the offending file:line, citing the required grammar

#### Scenario: Legacy REGO spelling still resolves to its RG code

- **GIVEN** a function carrying `# noqa: REGO-BODY-DUP -- legacy spelling, see ADR-NNNN` AND a sibling with matching `ast_hash_normalized`
- **AND** `REGO-BODY-DUP` aliases to `RG001`
- **WHEN** `body_dup.rego` runs
- **THEN** no `deny` is emitted for the suppressed function (the legacy code resolves to `RG001`)
