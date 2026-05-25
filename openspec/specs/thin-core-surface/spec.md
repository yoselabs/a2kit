# thin-core-surface Specification

## Purpose
TBD - created by archiving change simplify-and-thin-core. Update Purpose after archive.
## Requirements
### Requirement: FastMCP is a hard dependency; a2kit does not reinvent its primitives

The library SHALL declare `fastmcp` as a required dependency in `pyproject.toml`. Where FastMCP ships an equivalent primitive, a2kit SHALL NOT ship its own.

#### Scenario: FastMCP is required, not optional

- **WHEN** `pyproject.toml [project] dependencies` is inspected
- **THEN** `fastmcp` appears as a required dependency

#### Scenario: a2kit middleware chain is delegated

- **WHEN** the source tree is inspected
- **THEN** concrete a2kit-unique middlewares subclass `fastmcp.server.middleware.Middleware` and are registered through the FastMCP server

### Requirement: Thin core + plugin packages structure

The package SHALL be organized into a thin core at `src/a2kit/*.py` (top-level files only) and plugin packages under `src/a2kit/packages/<name>/`. a2kit core SHALL function without importing any plugin package. The specific set of core files and plugin packages is owned by the `module-layout-discipline` and `import-acyclicity` capabilities; this requirement asserts only the two-tier shape.

#### Scenario: Core works without plugins

- **WHEN** an MCP author imports from `a2kit` (top level only) and never references `a2kit.packages.*`
- **THEN** they can register tools, compose an `App`, and the core imports without pulling a plugin package

#### Scenario: Plugin packages live under packages/

- **WHEN** `ls src/a2kit/packages/` is run
- **THEN** the result lists the plugin packages, each a directory with its own `__init__.py`

### Requirement: No backwards compatibility shims

The library SHALL ship no compat shims, deprecated aliases, or "removed in next cycle" carryovers. A renamed symbol exists only under its new name; the old name is not aliased. The framework SHALL NOT emit `DeprecationWarning`.

#### Scenario: No deprecated aliases

- **WHEN** the source tree is grepped for `DeprecationWarning`
- **THEN** no a2kit-emitted `DeprecationWarning` exists

#### Scenario: No alias re-exports for renamed symbols

- **WHEN** a renamed symbol is searched
- **THEN** only the new name exists in the source; the old name is not aliased

### Requirement: Public-tier surface drift is gated by snapshot tests

The library SHALL enforce ADR 0004's tier discipline with snapshot
tests for Tier 1 (`a2kit.*`) and every Tier 2 (`a2kit.<domain>`) module.
A change to the set of public names exposed by any tier MUST appear as
a diff in the corresponding `tests/surface/expected_tier*.txt` file
and MUST be reviewed alongside any ADR amendment that justifies the
change.

#### Scenario: Adding a Tier-1 symbol requires a paired expectation diff

- **WHEN** a developer adds a name to `_LAZY_ATTRS` in
  `src/a2kit/__init__.py`
- **AND** does not update `tests/surface/expected_tier1.txt` or
  `expected_lazy_attrs.txt`
- **THEN** `make test` fails
- **AND** the failure message names the added symbol and references
  ADR 0004

#### Scenario: Demoting a symbol requires the same diff

- **WHEN** a developer moves a symbol from Tier 1 to a Tier-2 module
- **THEN** the Tier-1 expectation removes the name
- **AND** the Tier-2 expectation adds the name
- **AND** both diffs appear in the commit

