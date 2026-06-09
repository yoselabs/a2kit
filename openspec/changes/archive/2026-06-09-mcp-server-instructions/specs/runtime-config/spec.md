## ADDED Requirements

### Requirement: McpConfig.instructions sets the MCP server-level instructions

`McpConfig` SHALL expose a field `instructions: str | None` defaulting to `None`. The field carries the **server-level natural-language guidance** advertised to connecting MCP clients/agents (a short description of what the server is for and how to use its tools), corresponding to FastMCP's `instructions=` server parameter. The field SHALL be settable via env var `A2KIT_MCP__INSTRUCTIONS`, via `.env` file entry, or via `A2kitConfig(mcp=McpConfig(instructions="…"))` kwarg. Per ADR 0022's inverted source order, env wins over kwargs.

When `instructions` is `None` (the default), the MCP server build SHALL NOT pass a non-`None` `instructions` to the FastMCP server constructor — FastMCP's own default server-instructions behavior is preserved unchanged. When `instructions` is a string, the MCP server build SHALL thread that string into the FastMCP server's `instructions=` parameter so connecting clients receive it. A caller who supplies `instructions` directly through the raw-FastMCP escape hatch (`build_mcp_server(..., instructions=…)`) SHALL win over the config field (the escape hatch is not overridden).

This requirement is additive and non-breaking: absent an explicit value the behavior is byte-for-byte identical to today (no `instructions` field, none passed to FastMCP).

#### Scenario: Default instructions is None

- **GIVEN** no `A2KIT_MCP__INSTRUCTIONS` env var is set and no `.env` file with that key exists
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.mcp.instructions` is `None`

#### Scenario: Config instructions is threaded into the FastMCP server

- **GIVEN** an `App` whose `config.mcp.instructions` is `"Use entity_* tools for memory operations."`
- **WHEN** `build_mcp_server(app)` constructs the FastMCP server
- **THEN** the resulting FastMCP server's `instructions` equals `"Use entity_* tools for memory operations."`

#### Scenario: None default preserves today's FastMCP behavior

- **GIVEN** an `App` constructed with no explicit `instructions` and no `A2KIT_*` env vars set
- **WHEN** `build_mcp_server(app)` constructs the FastMCP server
- **THEN** the build does NOT pass a non-`None` `instructions` to `FastMCP.__init__`
- **AND** the server's instructions behavior is unchanged from before this field existed

#### Scenario: Env sets instructions

- **GIVEN** `A2KIT_MCP__INSTRUCTIONS=Operator server. Prefer the cli_* tools.` in process env
- **WHEN** `A2kitConfig()` is constructed
- **THEN** `cfg.mcp.instructions` is `"Operator server. Prefer the cli_* tools."`

#### Scenario: Env beats kwarg

- **GIVEN** `A2KIT_MCP__INSTRUCTIONS=from-env` in process env
- **WHEN** `A2kitConfig(mcp=McpConfig(instructions="from-code"))` is constructed
- **THEN** `cfg.mcp.instructions` is `"from-env"` (env wins per ADR 0022)

#### Scenario: Explicit escape-hatch instructions wins over config

- **GIVEN** an `App` whose `config.mcp.instructions` is `"from-config"`
- **WHEN** `build_mcp_server(app, instructions="from-caller")` is invoked
- **THEN** the resulting FastMCP server's `instructions` equals `"from-caller"`
