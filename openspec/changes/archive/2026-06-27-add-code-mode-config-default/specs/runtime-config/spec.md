## ADDED Requirements

### Requirement: McpConfig.code_mode is the consumer-owned code-mode default

`A2kitConfig.mcp.code_mode: bool` SHALL default to `True`. It carries the
App-author's **default** for whether the MCP server installs the
code-execution surface (the `search` / `get_schema` / `execute` meta-tools),
the same category of per-server-shape knob as `McpConfig.instructions` and
`McpConfig.structured_output`. The field SHALL be settable via env var
`A2KIT_MCP__CODE_MODE`, via `.env` entry, or via
`A2kitConfig(mcp=McpConfig(code_mode=…))` kwarg. Per ADR 0022's inverted source
order, env wins over kwargs.

The MCP server build SHALL consult this field only when its `code_mode`
parameter is unspecified (`None`); an explicit `build_mcp_server(..., code_mode=…)`
argument and an explicit `serve --code-mode/--no-code-mode` flag both win over
it. This requirement is additive and non-breaking: absent any override the
behavior is byte-for-byte identical to before the field existed (code mode on).

#### Scenario: Default code_mode is True

- **GIVEN** an `A2kitConfig` constructed with no overrides and no `A2KIT_*` env vars
- **WHEN** code reads `cfg.mcp.code_mode`
- **THEN** it is `True`

#### Scenario: Env sets code_mode

- **GIVEN** the environment has `A2KIT_MCP__CODE_MODE=false`
- **WHEN** an `A2kitConfig` is constructed
- **THEN** `cfg.mcp.code_mode` is `False`

#### Scenario: Env beats kwarg

- **GIVEN** the environment has `A2KIT_MCP__CODE_MODE=false`
- **WHEN** `A2kitConfig(mcp=McpConfig(code_mode=True))` is constructed
- **THEN** `cfg.mcp.code_mode` is `False` (env wins per ADR 0022)
