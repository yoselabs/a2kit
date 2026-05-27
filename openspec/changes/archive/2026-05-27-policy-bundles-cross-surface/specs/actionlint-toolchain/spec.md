## ADDED Requirements

### Requirement: `actionlint` is pinned in Makefile and verified by `make actionlint-check`

a2kit SHALL declare an `ACTIONLINT_VERSION` variable in `Makefile` and provide a `make actionlint-check` target that fails with a clear install hint when the binary is absent or the version does not match. The install-hint pattern SHALL mirror `make opa-check`: `brew install actionlint` for macOS, curl-to-`/usr/local/bin` instructions for Linux.

#### Scenario: actionlint present and version matches

- **GIVEN** `actionlint` is installed at the pinned version
- **WHEN** `make actionlint-check` runs
- **THEN** the target exits 0 with a success message

#### Scenario: actionlint absent

- **GIVEN** `actionlint` is not on `PATH`
- **WHEN** `make actionlint-check` runs
- **THEN** the target exits non-zero with a message naming the pinned version and showing per-platform install commands

#### Scenario: actionlint present but version mismatches

- **GIVEN** `actionlint` is installed at a version different from `ACTIONLINT_VERSION`
- **WHEN** `make actionlint-check` runs
- **THEN** the target exits non-zero with a message naming both versions and the install command for the pinned version

### Requirement: `make lint` gates on `actionlint` for `.github/workflows/*.yml`

`make lint` SHALL run `actionlint` against `.github/workflows/*.yml` before running the Rego layer. A non-zero exit from `actionlint` SHALL fail `make lint` immediately, before any Rego policy runs.

#### Scenario: workflow has a syntax error

- **GIVEN** a workflow file with malformed YAML or an invalid expression
- **WHEN** `make lint` runs
- **THEN** the target fails with `actionlint`'s findings printed to stderr; the Rego layer does not execute

#### Scenario: workflows are clean

- **GIVEN** all workflow files pass `actionlint`
- **WHEN** `make lint` runs
- **THEN** `actionlint` exits 0 and the Rego layer proceeds normally

### Requirement: `make bootstrap` documents the actionlint dependency

`make bootstrap` SHALL include `actionlint` alongside `opa` in its pre-flight check output, naming the binary, pinned version, and install hint when missing. Bootstrap SHALL NOT auto-install.

#### Scenario: bootstrap reports actionlint status

- **WHEN** `make bootstrap` runs
- **THEN** the output includes a line indicating whether `actionlint` is present at the pinned version, and an install hint when not
