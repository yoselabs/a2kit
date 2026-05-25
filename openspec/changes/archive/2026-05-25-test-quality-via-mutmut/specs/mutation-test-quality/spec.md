## ADDED Requirements

### Requirement: `mutmut` is configured + dev-dep

`mutmut>=2.5` SHALL be declared in `pyproject.toml [dependency-groups] dev`.
A `[tool.mutmut]` table SHALL configure `paths_to_mutate`, `tests_dir`,
`runner`, and an explicit `exclude` list.

#### Scenario: mutmut declared
- **WHEN** `pyproject.toml [dependency-groups] dev` is inspected
- **THEN** `"mutmut>=2.5"` (or higher minimum) appears

#### Scenario: tool config present
- **WHEN** `pyproject.toml [tool.mutmut]` is inspected
- **THEN** `paths_to_mutate = ["src/a2kit/"]`, `tests_dir = "tests/"`,
  `runner` references the project's pytest invocation, and an
  `exclude` array enumerates Protocol-only / dataclass-only modules
  with `# why:` comments

### Requirement: `make mutate*` targets

The Makefile SHALL expose `mutate`, `mutate-fast`, `mutate-show`, and
`mutate-html` targets.

#### Scenario: full mutation run
- **WHEN** a developer runs `make mutate`
- **THEN** the target invokes `uv run mutmut run` against `src/a2kit/`

#### Scenario: PR-time changed-files run
- **WHEN** a developer runs `make mutate-fast`
- **THEN** the target restricts `paths_to_mutate` to files changed
  since `origin/main` and runs `mutmut run` against that subset

#### Scenario: developer-facing report
- **WHEN** a developer runs `make mutate-show`
- **THEN** stdout lists every survived mutation with file path, line
  number, and the mutation diff

### Requirement: aggregate mutation-score floor

The aggregate mutation score across `src/a2kit/` SHALL be ≥ 90 %.
This floor is enforced by CI; falling below blocks merge to `main`.

#### Scenario: nightly run gates main
- **WHEN** the nightly CI workflow runs `make mutate` on `main`
- **THEN** the workflow exits non-zero if `mutmut results` reports an
  aggregate killed-fraction below 90 %

#### Scenario: PR run gates changed files
- **WHEN** the PR CI workflow runs `make mutate-fast`
- **THEN** the workflow exits non-zero if the changed-files mutation
  score drops below 80 %

### Requirement: mutation-score baseline tracking

A baseline mutation score SHALL be captured per CI run and exposed
via a README badge.

#### Scenario: README badge exists
- **WHEN** `README.md` is inspected after the nightly run
- **THEN** a mutation-score badge appears in the header section,
  reflecting the most recent aggregate score

### Requirement: exclusion list is explicit and justified

Files in `[tool.mutmut].exclude` SHALL each have a `# why:` comment
explaining the exemption (Protocol, pure-data class, namespace
`__init__`, etc.). No file is excluded "by default".

#### Scenario: Each excluded file is justified
- **WHEN** `[tool.mutmut].exclude` is inspected
- **THEN** every entry has an inline or adjacent `# why: <reason>` comment

#### Scenario: No bulk wildcards beyond `__init__.py`
- **WHEN** the `exclude` list is read
- **THEN** the only directory-spanning glob is `**/__init__.py`; all
  other entries are exact file paths
