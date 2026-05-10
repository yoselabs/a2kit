## ADDED Requirements

### Requirement: Docstring drives tool description

The system SHALL use the tool function's docstring (PEP 257 dedented) as the canonical description source for both MCP and CLI surfaces.

#### Scenario: first non-empty line becomes the short description

- **WHEN** a tool has a docstring whose first non-empty line is `"Fetch content from a URL."`
- **THEN** the MCP tool registration's `description` first line is `"Fetch content from a URL."` and the click subcommand's short-help is the same string

#### Scenario: full body forwarded to MCP description verbatim

- **WHEN** a tool has a multi-paragraph markdown docstring
- **THEN** the MCP tool registration's full `description` is the dedented body verbatim, markdown intact

#### Scenario: full body stripped of markdown for CLI long-help

- **WHEN** the same multi-paragraph docstring renders for `<app> <tool> --help`
- **THEN** the body appears with markdown markers stripped (bold/italic markers removed; links rendered as `text (url)`)

### Requirement: Per-parameter descriptions via `a2kit.Param`

The system SHALL accept `Annotated[T, a2kit.Param(description="...")]` on tool kwargs and forward the description to the MCP parameter schema and CLI option help.

#### Scenario: Param description forwarded to MCP schema

- **WHEN** a tool has `url: Annotated[str, a2kit.Param(description="Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`

#### Scenario: Param description forwarded to click help

- **WHEN** the same parameter is invoked via the CLI
- **THEN** `<app> <tool> --help` shows `--url ...` with the description string

### Requirement: Pydantic Field descriptions continue to work for body models

The system SHALL preserve the existing behavior where a tool kwarg that is a Pydantic model carries field descriptions via `pydantic.Field(description=...)`.

#### Scenario: model body kwarg uses Field descriptions

- **WHEN** a tool kwarg is a Pydantic model whose fields use `Field(description="...")`
- **THEN** those descriptions appear in the MCP input schema's nested object properties unchanged
