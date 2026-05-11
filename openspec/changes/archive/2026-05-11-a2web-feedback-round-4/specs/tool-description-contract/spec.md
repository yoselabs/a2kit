## MODIFIED Requirements

### Requirement: Per-parameter descriptions via `a2kit.Param`

The system SHALL accept `Annotated[T, a2kit.Param(description="...")]` on tool kwargs and forward the description to the MCP parameter schema and CLI option help. `a2kit.Param` SHALL also accept a single positional string argument as a shorthand for `description`. Mixing the positional and the `description=` kwarg in the same call SHALL raise `TypeError` at construction.

#### Scenario: Param description forwarded to MCP schema (kwargs form)

- **WHEN** a tool has `url: Annotated[str, a2kit.Param(description="Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`

#### Scenario: Param positional shorthand

- **WHEN** a tool has `url: Annotated[str, a2kit.Param("Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`
- **AND** the click subcommand option help is the same string

#### Scenario: Positional + description kwarg raises

- **WHEN** `a2kit.Param("first", description="second")` is constructed
- **THEN** `TypeError` is raised at construction time naming the conflict
