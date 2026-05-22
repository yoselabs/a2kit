# tool-description-contract Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
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

