# verb-decorators — replace-surfaces-with-visibility delta

## ADDED Requirements

### Requirement: `visibility` kwarg controls transport mounting tier

Verb decorators SHALL accept a `visibility` kwarg of type
`Literal["hidden", "cli", "all"] | None` with default `None`.
`None` means "inherit from the Router's `visibility` class
attribute (default `"all"`)". Tier semantics:

- `"hidden"` — CLI-invokable but absent from `--help` listing;
  not registered on any programmatic transport (MCP / future REST /
  future GraphQL).
- `"cli"` — visible in `--help`; not registered on programmatic
  transports.
- `"all"` — registered on every transport the App exposes (default).

#### Scenario: `visibility="hidden"` hides from --help and MCP
- **GIVEN** a tool `force_unlock` decorated `@a2kit.write(visibility="hidden")`
- **WHEN** the CLI is built and `<app> --help` runs
- **THEN** `force_unlock` is absent from the listing
- **AND** `<app> ops force_unlock` still executes when invoked directly
- **AND** the MCP server does not register `force_unlock`

#### Scenario: `visibility="cli"` excludes from MCP only
- **GIVEN** a tool `login` decorated `@a2kit.write(visibility="cli")`
- **WHEN** the MCP server is built
- **THEN** `login` is not in `server.list_tools()`
- **AND** `<app> connections login --help` runs successfully on the CLI

#### Scenario: Router class attr provides default
- **GIVEN** a Router class with `visibility = "cli"` and a tool with no `visibility=` kwarg
- **WHEN** the tool is registered on an App
- **THEN** its effective `meta.extras.visibility == "cli"`

#### Scenario: Per-tool kwarg overrides Router default
- **GIVEN** a Router class with `visibility = "cli"` and a tool decorated `@a2kit.read(visibility="all")`
- **WHEN** the tool is registered on an App
- **THEN** its effective `meta.extras.visibility == "all"`

