# lint-code-format Specification

## Purpose
TBD - created by archiving change ruff-compatible-lint-codes. Update Purpose after archive.
## Requirements
### Requirement: a2kit lint codes are ruff-noqa-grammar-safe

Every lint rule code emitted by a2kit SHALL match the regular expression `^[A-Z]+[0-9]+$` — a run of uppercase ASCII letters followed by a run of digits, with no hyphen or other separator. This SHALL hold across the static AST rules (`packages/lint/static.py`), the runtime checks (`packages/lint/runtime.py`), and the Rego-policy rules (`packages/lint/_bundle/policies/*.rego`). This is the grammar
ruff uses for `# noqa` codes, so a2kit codes and ruff codes can appear on
the same suppression line without either tool's parser corrupting the
other's codes.

Codes are organized into three reserved vendor prefixes, one per family,
and a2kit SHALL reserve `AK`, `AKR`, and `RG` as its lint-code prefixes:

- `AK` — static AST rules (e.g. `AK014`, `AK200`, `AK210`).
- `AKR` — runtime checks (e.g. `AKR001`).
- `RG` — Rego-policy rules (e.g. `RG001`, `RG002`, `RG010`).

No two rules SHALL resolve to the same code, within or across families.

#### Scenario: Every emitted code matches the ruff grammar

- **GIVEN** the full set of a2kit lint codes (static, runtime, rego)
- **WHEN** each code string is matched against `^[A-Z]+[0-9]+$`
- **THEN** every code matches
- **AND** no code contains a hyphen (the former `A2K-…` / `REGO-…` shapes are gone)

#### Scenario: A dashed legacy code no longer fires under its old spelling

- **GIVEN** the renamed layer rule (formerly `A2K-LAYER`, now `AK200`)
- **WHEN** the rule fires on a layering violation
- **THEN** the emitted `LintMessage.rule` is `AK200`
- **AND** no emitted finding carries a hyphenated code string

#### Scenario: Prefixes are reserved and non-overlapping

- **GIVEN** the reserved prefixes `AK`, `AKR`, `RG`
- **WHEN** the code set is partitioned by prefix
- **THEN** every code belongs to exactly one prefix family
- **AND** no two codes (within or across families) are equal

### Requirement: Inline `# noqa` grammar is a ruff superset and co-suppression-safe

a2kit SHALL parse inline suppression comments with the grammar
`# noqa[: <CODE>[, <CODE>]*] [ -- <reason text>]`, where each `<CODE>`
matches `^[A-Z]+[0-9]+$`. A bare `# noqa` (no codes) SHALL mean "suppress
every a2kit rule on this line" (wildcard). The literal reason separator
SHALL be ` -- ` (space-dash-dash-space) followed by free-text; the reason
is conventional for `AK*` / `AKR*` codes.

When a suppression line lists codes a2kit does not own (e.g. a ruff code
such as `S603`), a2kit SHALL ignore those foreign codes — they SHALL NOT
match any a2kit rule and SHALL NOT raise. Because all codes share the
ruff-compatible shape, a line carrying both an a2kit code and a ruff code
SHALL be parseable by both tools, each honoring only its own codes.

#### Scenario: Mixed a2kit + ruff codes on one line

- **GIVEN** a line carrying `# noqa: AK200, S603`
- **WHEN** a2kit's `parse_noqa` parses the line
- **THEN** the parsed code set is `{AK200, S603}`
- **AND** the a2kit rule `AK200` is suppressed on that line
- **AND** the foreign `S603` matches no a2kit rule and raises nothing

#### Scenario: Reason suffix is preserved and stripped from codes

- **GIVEN** a line carrying `# noqa: AK014 -- container stays under budget`
- **WHEN** `parse_noqa` parses the line
- **THEN** the parsed code set is `{AK014}` (the ` -- reason` is not parsed as a code)
- **AND** the rule `AK014` is suppressed on that line

#### Scenario: Bare noqa is a wildcard

- **GIVEN** a line carrying a bare `# noqa`
- **WHEN** any a2kit rule would fire on that line
- **THEN** it is suppressed (wildcard)

### Requirement: Legacy lint codes resolve through a frozen alias table

a2kit SHALL ship a frozen mapping `LEGACY_CODE_ALIASES` from each legacy
code (the former `A2K###`, `A2KR###`, `A2K-…`, and `REGO-…` spellings) to
its new ruff-safe code. The mapping SHALL be **complete** (every code
that existed before this change has exactly one entry), **injective** (no
two legacy codes map to the same new code), and every value SHALL match
`^[A-Z]+[0-9]+$`.

During the deprecation window, a2kit SHALL normalize a recognized legacy
code to its new code on *input* — in `# noqa:` suppression comments and
in the `[tool.a2kit.lint]` disable list — so existing consumer
suppressions and config keep working. Emitted findings SHALL always carry
the **new** code; a legacy spelling SHALL never appear as a
`LintMessage.rule`.

#### Scenario: Legacy suppression still resolves

- **GIVEN** a line carrying `# noqa: A2K-LAYER` (legacy spelling)
- **AND** `A2K-LAYER` aliases to `AK200`
- **WHEN** the renamed `AK200` rule would fire on that line
- **THEN** it is suppressed (the legacy code resolves to the new code)

#### Scenario: Legacy disable-list entry still disables the rule

- **GIVEN** `[tool.a2kit.lint] disabled = ["A2K014"]` in `pyproject.toml`
- **AND** `A2K014` aliases to `AK014`
- **WHEN** lint runs
- **THEN** the `AK014` rule is disabled

#### Scenario: Alias table is complete and injective

- **GIVEN** the `LEGACY_CODE_ALIASES` mapping
- **WHEN** it is checked against the full set of pre-change codes
- **THEN** every pre-change code is a key
- **AND** every value matches `^[A-Z]+[0-9]+$`
- **AND** no two keys share a value

#### Scenario: Findings never use a legacy spelling

- **GIVEN** any a2kit rule that fires
- **WHEN** its `LintMessage` is produced
- **THEN** `LintMessage.rule` matches `^[A-Z]+[0-9]+$` and is not a legacy code

### Requirement: Code rename preserves rule coverage without silent truncation

The migration to ruff-safe codes SHALL be a 1:1 rename of code strings
only — no rule's firing conditions, severity, or coverage SHALL change,
and no existing suppression or snapshot-represented rule SHALL be
dropped. The bulk rewrite of existing `# noqa:` suppressions and the
regeneration of lint snapshot fixtures SHALL each be guarded so that a
dropped or unrecognized code fails loudly rather than being silently
removed.

#### Scenario: noqa-line count is preserved across the sweep

- **GIVEN** the set of `# noqa:` lines in `src/` and `tests/` before the rename
- **WHEN** the bulk-suppression rewrite runs
- **THEN** the count of `# noqa:` lines after the rewrite is identical
- **AND** every code present after the rewrite is a value in `LEGACY_CODE_ALIASES`
- **AND** an unrecognized code aborts the rewrite rather than being dropped

#### Scenario: Snapshot rule coverage is preserved across regeneration

- **GIVEN** the set of rules represented in the lint snapshot fixtures before regeneration
- **WHEN** the fixtures are regenerated against the new codes
- **THEN** the set of rules represented after regeneration is identical (only spelling changed)
- **AND** every code in a regenerated fixture matches `^[A-Z]+[0-9]+$`

