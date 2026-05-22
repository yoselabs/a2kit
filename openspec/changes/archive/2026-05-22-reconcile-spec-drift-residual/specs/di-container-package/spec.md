## MODIFIED Requirements

### Requirement: DI container lives at `a2kit.packages.di`

The DI container module SHALL live at `src/a2kit/packages/di/`.
The package SHALL be **self-contained**: no `a2kit.*` imports inside the `a2kit/packages/di/` tree. A static lint check SHALL enforce this discipline. The package SHALL be structured to enable future extraction to a standalone PyPI distribution (separate `pyproject.toml` skeleton present, but the actual publish is out of scope for this change).

All a2kit modules that need container types, the `Resolver` protocol, or the `Scope` enum SHALL import from `a2kit.packages.di`.

#### Scenario: Container module is importable standalone

- **WHEN** a script outside the `a2kit` package tree imports `a2kit.packages.di`
- **THEN** the import succeeds
- **AND** `Container`, `Scope`, `Resolver`, `UnresolvableType` are accessible

#### Scenario: No a2kit imports inside the package

- **WHEN** `grep -rn "^from a2kit\|^import a2kit" src/a2kit/packages/di/` runs (excluding the `a2kit.packages.di.*` self-references)
- **THEN** the result is empty
- **AND** the lint check `a2kit lint static` enforces this with a dedicated rule code

#### Scenario: Container resolution types resolve from the package root

- **WHEN** a consumer imports the container surface from `a2kit.packages.di`
- **THEN** `Container`, `Scope`, `Resolver`, and `UnresolvableType` all resolve from that single package root
- **AND** no other module path exposes those container types
