# tool-description-contract delta

## MODIFIED Requirements

### Requirement: Pydantic Field descriptions continue to work for body models

The system SHALL preserve the existing behavior where a tool kwarg
that is a Pydantic model carries field descriptions via
`pydantic.Field(description=...)`. The CLI SHALL accept such body
models as a single JSON-string flag (`--<name> '<json>'`) and decode
via `Model.model_validate_json` inside the command callback. The MCP
wire shape for body-model parameters SHALL remain a structured
object (unchanged).

#### Scenario: model body kwarg uses Field descriptions

- **WHEN** a tool kwarg is a Pydantic model whose fields use `Field(description="...")`
- **THEN** those descriptions appear in the MCP input schema's nested object properties unchanged

#### Scenario: model body kwarg on the CLI takes a JSON string

- **GIVEN** a tool `async def submit(*, body: SubmitBody) -> ...` where `SubmitBody(BaseModel)` has fields `title: str`, `count: int`
- **WHEN** the user runs `<app> <router> submit --body '{"title":"x","count":3}'`
- **THEN** the CLI exposes a single `--body TEXT` option (not flattened per-field flags)
- **AND** the callback decodes the JSON string via `SubmitBody.model_validate_json(value)` before invoking the tool
- **AND** an invalid JSON payload raises a Click-style usage error naming the `--body` option

#### Scenario: MCP path for the same tool is unchanged

- **GIVEN** the same `submit` tool above
- **WHEN** an MCP client invokes the tool with `{"body": {"title": "x", "count": 3}}`
- **THEN** the structured object reaches the tool unchanged; no JSON-string round-trip happens on the MCP transport

### Requirement: Per-parameter descriptions via `a2kit.Param`

The system SHALL accept `Annotated[T, a2kit.Param(description="...")]`
on tool kwargs and forward the description to the MCP parameter
schema and CLI option help. `a2kit.Param` SHALL also accept a single
positional string argument as a shorthand for `description`. Mixing
the positional and the `description=` kwarg in the same call SHALL
raise `TypeError` at construction. On the CLI surface, the
description SHALL surface through Typer's `--help` rendering (via
the internal `_field_to_typer` adapter that rewrites `Annotated`
metadata into `typer.Option(help=...)` at command-build time).

#### Scenario: Param description forwarded to MCP schema (kwargs form)

- **WHEN** a tool has `url: Annotated[str, a2kit.Param(description="Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`

#### Scenario: Param description forwarded to Typer-rendered help

- **WHEN** the same parameter is invoked via the CLI
- **THEN** `<app> <tool> --help` shows `--url ...` with the description string, rendered by Typer

#### Scenario: Param positional shorthand

- **WHEN** a tool has `url: Annotated[str, a2kit.Param("Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`
- **AND** the CLI subcommand option help is the same string

#### Scenario: Positional + description kwarg raises

- **WHEN** `a2kit.Param("first", description="second")` is constructed
- **THEN** `TypeError` is raised at construction time naming the conflict
