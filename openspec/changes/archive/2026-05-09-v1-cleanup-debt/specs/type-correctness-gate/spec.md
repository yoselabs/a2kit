## ADDED Requirements

### Requirement: ty type-checks pass on `src/` with zero errors

The repository SHALL pass `uv run ty check src/` with **zero diagnostics**
(no errors, no warnings) on every commit to `main`. ty is a hard CI gate
alongside ruff and `a2kit lint static`.

#### Scenario: Hard gate in `make lint`
- **WHEN** a developer runs `make lint`
- **THEN** the target invokes `uv run ty check src/` and exits non-zero if
  ty reports any diagnostic

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

### Requirement: ty diagnostics suppressed only via inline `# ty: ignore[code]`

In source files under `src/a2kit/`, ty diagnostics MAY be suppressed with
inline `# ty: ignore[<rule-code>]` comments. Each such comment SHALL include
a `# why:` explanation on the same line or the line above. The total count
of `# ty: ignore` comments across `src/a2kit/` SHALL be ≤ 10.

#### Scenario: Inline ignore has rationale
- **WHEN** a file contains `# ty: ignore[<code>]`
- **THEN** an adjacent `# why: ...` comment explains the third-party-stub
  or framework constraint forcing the suppression

#### Scenario: Ignore budget enforced
- **WHEN** `grep -rE "# ty: ignore" src/a2kit/ | wc -l` runs
- **THEN** the count is ≤ 10

### Requirement: Dev dependency `ty` is pinned

The `ty` dev dependency SHALL be declared with a minimum version constraint
in `pyproject.toml [dependency-groups] dev`. Bumps are deliberate.

#### Scenario: ty in dev deps
- **WHEN** `pyproject.toml` is inspected
- **THEN** the `[dependency-groups] dev` array contains `"ty>=0.0.34"`
  (or higher minimum)
