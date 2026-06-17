# Rego policy layer

## Purpose

Architectural-invariant enforcement via Open Policy Agent (OPA) Rego policies, fed by a stable AST-fact extractor. Distinct from `a2kit lint static`: this layer polices cross-codebase and cross-surface invariants (not per-file authoring patterns). See ADR 0024, ADR 0026.
## Requirements
### Requirement: `extract_facts.py` emits a stable curated-AST projection

a2kit SHALL provide `scripts/extract_facts.py` that walks `src/**/*.py`, parses each module with the stdlib `ast`, and emits a single JSON document on stdout conforming to the documented schema (printable via `--schema`).

The schema SHALL include at minimum:
- `functions: [{file, name, line, kind, is_async, is_private, body_stmt_count, ast_hash_normalized}]`
- `modules: [{file, has_module_getattr, top_level_assignments}]`
- `suppressions: [{file, line, rule_id, reason}]`
- `workflows: [{file, name, permissions, on, jobs: [{name, permissions, steps: [{uses, uses_ref, has_pinned_sha, vendor, with_keys}]}]}]`
- `pyproject: {dependencies: [{name, spec, has_upper_bound}], optional_dependencies: {<group>: [{name, spec, has_upper_bound}]}, build_system_requires: [{name, spec, has_upper_bound}]}`

`ast_hash_normalized` SHALL be a SHA-256 hex digest of the function body's `ast.dump(...)` after: identifier `Name.id` / `arg.arg` / `Attribute.attr` replaced with sentinel `_ID_`; literal `Constant.value` replaced with `_LIT_`; type annotations stripped.

`has_pinned_sha` (workflows) SHALL be `true` iff the `uses:` reference is a 40-character lowercase-hex SHA. `vendor` SHALL be the first path component of `uses` (e.g. `actions` for `actions/checkout@v4`). Both fields SHALL be pre-computed in extract, not in Rego.

`has_upper_bound` (pyproject) SHALL be `true` iff the version specifier contains `<`, `<=`, or `~=`. Bare names, `>=`-only, and `*` SHALL be `false`. `^` (PEP 621 disallows) SHALL be `false`.

Extract SHALL be a pure function of the input tree: same tree → same JSON, byte-for-byte. No clock reads, no env reads, no network. Workflow YAML SHALL be parsed with `pyyaml` (`yaml.safe_load`); `pyproject.toml` SHALL be parsed with stdlib `tomllib`.

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

#### Scenario: Workflows collection captures uses-pin detection

- **GIVEN** `.github/workflows/x.yml` with one job, one step `uses: actions/checkout@a81bbbf` (7-char abbrev)
- **WHEN** `extract_facts.py` runs
- **THEN** the workflow entry has `jobs[0].steps[0].uses_ref == "a81bbbf"`, `has_pinned_sha == false`, `vendor == "actions"`

#### Scenario: Workflows collection captures pinned-SHA detection

- **GIVEN** a step `uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11` (40-char SHA)
- **WHEN** `extract_facts.py` runs
- **THEN** that step's `has_pinned_sha == true`

#### Scenario: Pyproject upper-bound detection

- **GIVEN** `pyproject.toml` with dependencies `fastapi>=0.115,<0.130`, `httpx`, `pydantic>=2`, `click~=8.1`
- **WHEN** `extract_facts.py` runs
- **THEN** the pyproject entry has those four deps with `has_upper_bound` values `true, false, false, true` respectively

### Requirement: `body_dup.rego` flags cross-file body duplication, modulo allowlist

`policies/body_dup.rego` SHALL emit a `deny` finding for every pair of functions `(i, j)` such that: `i.file != j.file` AND `i.ast_hash_normalized == j.ast_hash_normalized` AND `i.body_stmt_count >= 3` AND neither name appears in any `policies/allowlist.json` `body_dup` entry.

#### Scenario: R6 (log formatter dup) fires before resolution

- **GIVEN** the current `packages/log/wire.py:21` and `packages/context/stderr.py:337` (both implementing `_cap_text` / `_format_kv` shape)
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

### Requirement: Allowlist entries require a reason

`policies/allowlist.json` SHALL be a JSON object with per-policy sections, each section a list of `{names: [...], reason: "<non-empty>"}` entries. An entry without `reason`, or with empty `reason`, SHALL cause policy load to fail.

#### Scenario: Allowlist without reason fails policy load

- **GIVEN** `policies/allowlist.json` contains an entry `{"names": ["_foo"]}` (no reason)
- **WHEN** `a2kit lint rego` runs
- **THEN** the wrapper exits non-zero with a clear error naming the bad entry

### Requirement: `a2kit lint rego` integrates Rego findings into the lint pipeline

`a2kit lint rego [paths...]` SHALL invoke `extract_facts.py`, pipe the JSON to `opa eval --bundle policies/ --input <facts.json> --format json 'data.a2kit.deny'`, parse findings, and emit them in the same finding shape as `a2kit lint static`. Any `deny` finding SHALL cause exit code 1. The subcommand SHALL be wired into `make lint` after `a2kit lint static` and after `actionlint`.

#### Scenario: Clean tree exits zero

- **GIVEN** a tree with no policy violations
- **WHEN** `a2kit lint rego src/` runs
- **THEN** exit code is 0 and stdout is empty (or matches `a2kit lint static`'s clean-run shape)

#### Scenario: Dirty tree exits non-zero with structured findings

- **GIVEN** a tree containing a known body-dup pair
- **WHEN** `a2kit lint rego src/` runs
- **THEN** exit code is 1 and findings carry rule ID `REGO-BODY-DUP` with both file:line locations

#### Scenario: Findings span policy domains in one invocation

- **GIVEN** one body-dup violation, one workflow with an unpinned `uses:`, and one pyproject dep without an upper bound
- **WHEN** `a2kit lint rego` runs
- **THEN** exit code is 1 and the findings list includes one each of `REGO-BODY-DUP`, `REGO-GHA-PIN-SHA`, and `REGO-PYPROJECT-UPPER-BOUND`

### Requirement: jscpd is removed; body_dup.rego is the regression gate

`.jscpd.json`, `package.json`, `pnpm-lock.yaml`, and any `pnpm install` step from project bootstrap docs SHALL be deleted. Calibration on 2026-05-27 (`STRUCTURE_ISSUES.md`) demonstrated that body_dup.rego at the normalized-hash level catches a strict superset of what jscpd at any tuning catches, with no additional false positives.

#### Scenario: jscpd files are absent post-change

- **WHEN** the change lands
- **THEN** `.jscpd.json`, `package.json`, `pnpm-lock.yaml` do not exist in the working tree
- **AND** `rg pnpm` returns no matches in docs or Makefile

### Requirement: `github_actions.rego` flags unpinned third-party action SHAs

`policies/github_actions.rego` SHALL emit a `REGO-GHA-PIN-SHA` `deny` finding for every workflow step where `step.uses != null` AND `step.has_pinned_sha == false` AND `step.vendor` is NOT in the `policies/data.json` `a2kit.allowlist.github_actions_vendor_unpinned` allowlist.

The intent: third-party actions execute arbitrary code in CI; pinning to a 40-char SHA prevents tag-mutation supply-chain attacks. First-party vendors (`actions/`) MAY be allowlisted explicitly with documented reason.

#### Scenario: Unpinned vendor action is flagged

- **GIVEN** a workflow step `uses: tj-actions/changed-files@v1` (tag, not SHA)
- **WHEN** `github_actions.rego` runs
- **THEN** a `REGO-GHA-PIN-SHA` `deny` is emitted naming `tj-actions/changed-files`, the workflow file, and job

#### Scenario: SHA-pinned action passes

- **GIVEN** a step `uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11`
- **WHEN** `github_actions.rego` runs
- **THEN** no `REGO-GHA-PIN-SHA` `deny` is emitted for that step

#### Scenario: Allowlisted vendor exempted

- **GIVEN** `policies/data.json` `a2kit.allowlist.github_actions_vendor_unpinned` contains `{vendor: "actions", reason: "official GitHub actions, mutation risk accepted"}` AND a step `uses: actions/setup-python@v5`
- **WHEN** `github_actions.rego` runs
- **THEN** no `REGO-GHA-PIN-SHA` `deny` is emitted for that step

### Requirement: `github_actions.rego` flags workflows without a top-level permissions block

`policies/github_actions.rego` SHALL emit a `REGO-GHA-PERMISSIONS` `deny` finding for every workflow file with `permissions == null` at the top level. Per-job `permissions:` SHALL satisfy the requirement only if the workflow also declares a top-level block (defense in depth).

#### Scenario: Missing top-level permissions fires

- **GIVEN** `.github/workflows/x.yml` with no top-level `permissions:` key
- **WHEN** `github_actions.rego` runs
- **THEN** a `REGO-GHA-PERMISSIONS` `deny` is emitted naming the file

#### Scenario: Top-level permissions present passes

- **GIVEN** a workflow with top-level `permissions: {contents: read}`
- **WHEN** `github_actions.rego` runs
- **THEN** no `REGO-GHA-PERMISSIONS` `deny` is emitted for that file

### Requirement: `github_actions.rego` flags third-party vendors not on the allowlist

`policies/github_actions.rego` SHALL emit a `REGO-GHA-VENDOR-ALLOW` `deny` finding for every workflow step where `step.uses != null` AND `step.vendor` is NOT in `policies/data.json` `a2kit.allowlist.github_actions_vendor`. The allowlist seeds with at minimum `actions` (GitHub official) and `astral-sh` (uv/ruff vendor); additions require documented reason.

#### Scenario: Unknown vendor fires

- **GIVEN** a step `uses: someone-untrusted/spooky-action@<sha>` AND `someone-untrusted` not on the allowlist
- **WHEN** `github_actions.rego` runs
- **THEN** a `REGO-GHA-VENDOR-ALLOW` `deny` is emitted naming the vendor

#### Scenario: Allowlisted vendor passes

- **GIVEN** a step `uses: astral-sh/setup-uv@<sha>` AND `astral-sh` on the allowlist
- **WHEN** `github_actions.rego` runs
- **THEN** no `REGO-GHA-VENDOR-ALLOW` `deny` is emitted

### Requirement: `pyproject.rego` flags runtime dependencies without an upper bound

`policies/pyproject.rego` SHALL emit a `REGO-PYPROJECT-UPPER-BOUND` `deny` finding for every entry in `pyproject.dependencies` where `has_upper_bound == false` AND the dep name is NOT in `policies/data.json` `a2kit.allowlist.pyproject_upper_bound`.

`pyproject.optional_dependencies` and dev/test extras are exempt from this rule.

#### Scenario: Bare dep name fires

- **GIVEN** `pyproject.toml` `[project] dependencies = ["httpx"]`
- **WHEN** `pyproject.rego` runs
- **THEN** a `REGO-PYPROJECT-UPPER-BOUND` `deny` is emitted naming `httpx`

#### Scenario: Dep with upper bound passes

- **GIVEN** `dependencies = ["fastapi>=0.115,<0.130"]`
- **WHEN** `pyproject.rego` runs
- **THEN** no `REGO-PYPROJECT-UPPER-BOUND` `deny` is emitted for `fastapi`

#### Scenario: Optional / dev extras exempt

- **GIVEN** `[project.optional-dependencies] test = ["pytest"]` (no upper bound)
- **WHEN** `pyproject.rego` runs
- **THEN** no `REGO-PYPROJECT-UPPER-BOUND` `deny` is emitted for `pytest`

#### Scenario: Allowlisted runtime dep exempt

- **GIVEN** `dependencies = ["fastmcp"]` AND `policies/data.json` `a2kit.allowlist.pyproject_upper_bound` contains `{name: "fastmcp", reason: "pre-1.0; pin via uv.lock"}`
- **WHEN** `pyproject.rego` runs
- **THEN** no `REGO-PYPROJECT-UPPER-BOUND` `deny` is emitted for `fastmcp`

