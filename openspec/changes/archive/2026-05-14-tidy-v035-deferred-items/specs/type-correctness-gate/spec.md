## MODIFIED Requirements

### Requirement: ty type-checks pass on `src/` with zero errors

The repository SHALL pass `uv run ty check src/` AND `uv run ty check tests/` with **zero diagnostics** (no errors, no warnings) on every commit to `main`. ty is a hard CI gate alongside ruff and `a2kit lint static`. The `tests/` invocation SHALL NOT relax the rule set relative to `src/`.

#### Scenario: Hard gate in `make lint`
- **WHEN** a developer runs `make lint`
- **THEN** the target invokes `uv run ty check src/` AND `uv run ty check tests/` and exits non-zero if either reports any diagnostic

#### Scenario: ty config in pyproject.toml
- **WHEN** `pyproject.toml` is inspected
- **THEN** a `[tool.ty.rules]` table exists declaring per-rule severity
  overrides for known third-party-stub limitations (e.g. `_Wrapped` from
  `functools.wraps` lacking `__signature__` in stubs); each override has a
  `# why: ...` rationale comment

#### Scenario: No global rule disables
- **WHEN** `[tool.ty.rules]` is read
- **THEN** no rule is set to `"ignore"` globally; severity is lowered only
  for specific rules with documented rationale, never silenced

#### Scenario: every `# ty: ignore` in tests/ carries a `# why:` rationale

- **WHEN** any line under `tests/` contains `# ty: ignore[...]`
- **THEN** the same line OR the line immediately above carries a `# why:` rationale comment naming the intentional pattern (e.g. "passing invalid type to assert error path", "exercising removed surface for migration test")
