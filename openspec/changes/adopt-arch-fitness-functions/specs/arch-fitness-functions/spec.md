## ADDED Requirements

### Requirement: Tach is the declarative module-boundary enforcer

The repository SHALL carry a top-level `tach.toml` that models every package under `src/a2kit/packages/*`. Each package module SHALL declare its `depends_on` list explicitly; the empty list MUST be the default for a leaf package. The `a2kit` root module SHALL declare its allowed package dependencies. Running `tach check` SHALL exit non-zero on any import that violates a declared boundary.

#### Scenario: tach check passes on a clean tree

- **WHEN** `tach check` runs on the post-sync tree
- **THEN** the command exits 0
- **AND** no boundary violations are reported

#### Scenario: cross-package import fails the gate

- **GIVEN** `tach.toml` declares `a2kit.packages.cli.depends_on = []`
- **WHEN** a contributor adds `from a2kit.packages.mcp import X` to a file in `packages/cli/`
- **THEN** `tach check` exits non-zero
- **AND** the violation is reported with file + line

#### Scenario: domain imports from packages fail the gate

- **GIVEN** `tach.toml` declares `a2kit.packages.<name>.depends_on = []` for every leaf package
- **WHEN** a contributor adds `from a2kit.app import App` to a file in `packages/<name>/`
- **THEN** `tach check` exits non-zero

### Requirement: pytest-archon hosts AST-level / call-site rules

The repository SHALL carry a `tests/architecture/` package containing pytest-archon test modules. Each rule SHALL be expressible as a single pytest function. The suite SHALL be runnable as `uv run pytest tests/architecture -q` and SHALL be wired into the default lint gate.

#### Scenario: archon suite collects under standard pytest

- **WHEN** `uv run pytest tests/architecture -q` runs
- **THEN** every module under `tests/architecture/` is collected
- **AND** at least three rules execute (init-purity, tool-returns-pydantic, no-dict-str-any-on-internal-dataclasses)

#### Scenario: `__init__.py` purity rule rejects private re-exports

- **GIVEN** a package `packages/foo/__init__.py` that does `from ._impl import _internal_thing`
- **WHEN** `test_packages_init_is_only_public_surface` runs
- **THEN** the rule fails and names the offending re-export

### Requirement: `make arch` is the umbrella structural gate

The Makefile SHALL define an `arch` target invoking, in order, `tach check` and the pytest-archon suite. The target SHALL fail fast on the first non-zero exit. `make lint` (or the project's umbrella check target) SHALL invoke `make arch` and fail on its non-zero exit. CI SHALL fail on `make arch` non-zero exit.

#### Scenario: make arch wires both tools

- **WHEN** `make arch` runs
- **THEN** Tach runs first
- **AND** the archon suite runs second
- **AND** the target exits 0 only if both succeed
