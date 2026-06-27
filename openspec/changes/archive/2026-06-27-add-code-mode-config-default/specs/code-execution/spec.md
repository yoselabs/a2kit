## MODIFIED Requirements

### Requirement: Code execution is a bundled, default-on MCP surface

When an a2kit MCP server is built with code mode enabled, the server SHALL
install FastMCP's `CodeMode` transform. The transform collapses the listed tool
catalog: `list_tools` returns only the discovery and execute meta-tools
(`search`, `get_schema`, `execute`). The server's real tools remain callable by
name but are no longer enumerated. The tool author writes nothing to obtain
this surface.

Whether code mode is enabled SHALL be resolved as a tri-state:
`build_mcp_server`'s `code_mode` parameter SHALL be `bool | None` defaulting to
`None`. When `None`, the build SHALL consult `runtime.config.mcp.code_mode`
(itself defaulting to `True`); an explicit `True`/`False` argument SHALL win
over config. With no config override and no explicit argument, code mode is
enabled — byte-for-byte today's behavior.

#### Scenario: Default build installs code mode

- **GIVEN** an `a2kit.App` with one or more registered tools and no
  `A2KIT_MCP__CODE_MODE` override
- **WHEN** `build_mcp_server(app)` runs with no `code_mode` argument
- **THEN** the returned server's `list_tools` returns exactly `search`, `get_schema`, and `execute`
- **AND** each real tool is still invocable by its own name via `call_tool`

#### Scenario: Config default disables code mode

- **GIVEN** an `a2kit.App` whose `config.mcp.code_mode` is `False`
- **WHEN** `build_mcp_server(app)` runs with no `code_mode` argument
- **THEN** the server exposes every registered tool in `list_tools`
- **AND** no `execute`, `search`, or `get_schema` meta-tool is present

#### Scenario: Explicit argument wins over config

- **GIVEN** an `a2kit.App` whose `config.mcp.code_mode` is `True`
- **WHEN** `build_mcp_server(app, code_mode=False)` runs
- **THEN** no code-mode meta-tools are present (the explicit `False` wins)

#### Scenario: Author writes nothing

- **WHEN** a tool author registers a tool with `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`
- **THEN** that tool is reachable through the `execute` sandbox with no additional author code, annotation, or registration

## REMOVED Requirements

### Requirement: The `--code-mode-off` toggle disables the surface

**Reason:** The one-directional `--code-mode-off` flag is replaced by the
bidirectional, absolute `--code-mode / --no-code-mode` pair (see the added
requirement below) and the new `config.mcp.code_mode` default. The old spelling
is removed outright (no backward-compat shim, AGENTS.md §1); `--no-code-mode`
or `config.mcp.code_mode=False` is the migration.

## ADDED Requirements

### Requirement: The serve CLI overrides the code-mode default both directions

Code execution SHALL be overridable per-invocation by a bidirectional flag
pair. The `serve` command SHALL accept `--code-mode` (force ON) and
`--no-code-mode` (force OFF) as a single `Optional[bool]` option defaulting to
unspecified. An explicit flag SHALL thread its value into `build_mcp_server`'s
`code_mode`; when neither flag is given, `serve` SHALL pass `None` so the
configured default (then the built-in default) decides. The flag is **absolute**
— its effect does not depend on the configured default. The previous
`--code-mode-off` spelling SHALL NOT be accepted.

#### Scenario: serve forces code mode off

- **WHEN** the server is started with `serve --no-code-mode`
- **THEN** the running server exposes the full real tool catalog and no code-mode meta-tools

#### Scenario: serve forces code mode on over a config-off default

- **GIVEN** an App whose `config.mcp.code_mode` is `False`
- **WHEN** the server is started with `serve --code-mode`
- **THEN** the running server exposes the `search` / `get_schema` / `execute` meta-tools

#### Scenario: serve defers to config when no flag is given

- **WHEN** the server is started with `serve` and neither code-mode flag
- **THEN** `build_mcp_server` receives `code_mode=None`
- **AND** `runtime.config.mcp.code_mode` decides whether the transform installs

#### Scenario: the old flag spelling is gone

- **WHEN** the server is started with `serve --code-mode-off`
- **THEN** the CLI rejects it as an unknown option
