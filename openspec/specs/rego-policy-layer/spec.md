## ADDED Requirements

### Requirement: `extract_facts.py` emits a stable curated-AST projection

a2kit SHALL provide `scripts/extract_facts.py` that walks `src/**/*.py`, parses each module with the stdlib `ast`, and emits a single JSON document on stdout conforming to the documented schema (printable via `--schema`).

The schema SHALL include at minimum:
- `functions: [{file, name, line, kind, is_async, is_private, body_stmt_count, ast_hash_normalized}]`
- `modules: [{file, has_module_getattr, top_level_assignments}]`
- `suppressions: [{file, line, rule_id, reason}]`

`ast_hash_normalized` SHALL be a SHA-256 hex digest of the function body's `ast.dump(...)` after: identifier `Name.id` / `arg.arg` / `Attribute.attr` replaced with sentinel `_ID_`; literal `Constant.value` replaced with `_LIT_`; type annotations stripped.

Extract SHALL be a pure function of the input tree: same tree → same JSON, byte-for-byte. No clock reads, no env reads, no network.

#### Scenario: Two functions with identical bodies and different identifiers hash identically

- **GIVEN** `def f(x): return x + 1` in file A and `def g(y): return y + 1` in file B
- **WHEN** `extract_facts.py` runs over both
- **THEN** the two functions' `ast_hash_normalized` values are equal

#### Scenario: Two functions with different shapes hash differently

- **GIVEN** `def f(x): return x + 1` and `def g(x): return x * 2`
- **WHEN** `extract_facts.py` runs over both
- **THEN** the two `ast_hash_normalized` values differ

#### Scenario: Extract is reproducible

- **WHEN** `extract_facts.py` runs twice over an unchanged tree
- **THEN** the two outputs are byte-identical

### Requirement: `body_dup.rego` flags cross-file body duplication, modulo allowlist

`policies/body_dup.rego` SHALL emit a `deny` finding for every pair of functions `(i, j)` such that: `i.file != j.file` AND `i.ast_hash_normalized == j.ast_hash_normalized` AND `i.body_stmt_count >= 3` AND neither name appears in any `policies/allowlist.json` `body_dup` entry.

#### Scenario: R6 (LDD formatter dup) fires before resolution

- **GIVEN** the current `packages/ldd/wire.py:21` and `packages/context/stderr.py:337` (both implementing `_cap_text` / `_format_kv` shape)
- **WHEN** `body_dup.rego` runs against extracted facts
- **THEN** a `deny` finding names both locations with rule ID `REGO-BODY-DUP`

#### Scenario: Body-dup respects the 3-statement floor

- **GIVEN** two functions with identical 2-statement bodies in different files
- **WHEN** `body_dup.rego` runs
- **THEN** no `deny` is emitted (filtered by `body_stmt_count >= 3`)

#### Scenario: Allowlist drops a known-acceptable convergent pair

- **GIVEN** functions `_foo` in file A and `_foo` in file B with matching hash, AND `policies/allowlist.json` `body_dup` entry `{names: ["_foo"], reason: "intentional parallel impl, see ADR-NNNN"}`
- **WHEN** `body_dup.rego` runs
- **THEN** no `deny` is emitted for the pair

### Requirement: `name_collision.rego` flags cross-file private-helper name reuse, modulo allowlist

`policies/name_collision.rego` SHALL emit a `deny` finding for every `_`-prefixed (and not dunder, i.e., not starting with `__`) function name appearing in 2 or more distinct files, unless the name is in `policies/allowlist.json` `name_collision` entries.

#### Scenario: R1 (`_call` duplication) fires before resolution

- **GIVEN** `async def _call` at `packages/dispatch/envelope.py:69` and `packages/dispatch/stages.py:33`
- **WHEN** `name_collision.rego` runs against extracted facts
- **THEN** a `deny` finding names both locations with rule ID `REGO-NAME-COLLISION`

#### Scenario: Dunder names are exempt

- **GIVEN** `__getattr__` defined at module scope in 7 different files
- **WHEN** `name_collision.rego` runs
- **THEN** no `deny` is emitted (dunder names exempt by rule, not by allowlist)

### Requirement: `noqa -- reason` suppression filters policy findings

Every Rego policy SHALL filter its `deny` set against the `suppressions` fact set before emission. A function carrying `# noqa: <RULE-ID> -- <reason text>` SHALL be excluded from findings of that rule ID. The grammar matches the project convention landed in commit `83819db` (`feat(lint): A2K-NO-DICT-STR-ANY + noqa --reason grammar`): the literal separator is ` -- ` (space-dash-dash-space) followed by free-text reason; no `--reason` keyword, no quotes required. For REGO-* findings, a `# noqa: REGO-*` without a ` -- ` reason suffix SHALL be a hard structural error (stronger than existing A2K-* rules, where reasons are conventional). Rationale: Rego policies enforce architectural invariants; every suppression must be justified.

#### Scenario: noqa with reason suppresses the finding

- **GIVEN** a function carrying `# noqa: REGO-BODY-DUP -- intentional parallel impl, see ADR-NNNN` AND a sibling function with matching `ast_hash_normalized`
- **WHEN** `body_dup.rego` runs
- **THEN** no `deny` is emitted for the suppressed function

#### Scenario: REGO noqa without reason is a hard error

- **GIVEN** a function carrying `# noqa: REGO-BODY-DUP` (no ` -- ` reason)
- **WHEN** `extract_facts.py` runs
- **THEN** the extractor exits non-zero and names the offending file:line, citing the required grammar

### Requirement: Allowlist entries require a reason

`policies/allowlist.json` SHALL be a JSON object with per-policy sections, each section a list of `{names: [...], reason: "<non-empty>"}` entries. An entry without `reason`, or with empty `reason`, SHALL cause policy load to fail.

#### Scenario: Allowlist without reason fails policy load

- **GIVEN** `policies/allowlist.json` contains an entry `{"names": ["_foo"]}` (no reason)
- **WHEN** `a2kit lint rego` runs
- **THEN** the wrapper exits non-zero with a clear error naming the bad entry

### Requirement: `a2kit lint rego` integrates Rego findings into the lint pipeline

`a2kit lint rego [paths...]` SHALL invoke `extract_facts.py`, pipe the JSON to `opa eval --bundle policies/ --input <facts.json> --format json 'data.a2kit.deny'`, parse findings, and emit them in the same finding shape as `a2kit lint static`. Any `deny` finding SHALL cause exit code 1. The subcommand SHALL be wired into `make lint` after `a2kit lint static`.

#### Scenario: Clean tree exits zero

- **GIVEN** a tree with no policy violations
- **WHEN** `a2kit lint rego src/` runs
- **THEN** exit code is 0 and stdout is empty (or matches `a2kit lint static`'s clean-run shape)

#### Scenario: Dirty tree exits non-zero with structured findings

- **GIVEN** a tree containing a known body-dup pair
- **WHEN** `a2kit lint rego src/` runs
- **THEN** exit code is 1 and findings carry rule ID `REGO-BODY-DUP` with both file:line locations

### Requirement: jscpd is removed; body_dup.rego is the regression gate

`.jscpd.json`, `package.json`, `pnpm-lock.yaml`, and any `pnpm install` step from project bootstrap docs SHALL be deleted. Calibration on 2026-05-27 (`STRUCTURE_ISSUES.md`) demonstrated that body_dup.rego at the normalized-hash level catches a strict superset of what jscpd at any tuning catches, with no additional false positives.

#### Scenario: jscpd files are absent post-change

- **WHEN** the change lands
- **THEN** `.jscpd.json`, `package.json`, `pnpm-lock.yaml` do not exist in the working tree
- **AND** `rg pnpm` returns no matches in docs or Makefile
