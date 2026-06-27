# code-execution Specification

## Purpose
TBD - created by archiving change code-execution-surface. Update Purpose after archive.
## Requirements
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

### Requirement: Destructive tools are gated out of the sandbox by default

The catalog reachable from the sandbox SHALL exclude every tool flagged `destructive`. Both discovery (`search`, `get_schema`) and `execute`'s `call_tool` SHALL refuse a `destructive` tool when the operator has not granted destructive reach. The grant SHALL be an operator-side setting — `serve --code-mode-allow-destructive`, mirrored in configuration — and SHALL NOT be expressible as a per-call argument to the `execute` tool.

#### Scenario: Destructive tool absent from sandbox catalog by default

- **GIVEN** a tool registered with `@a2kit.write(destructive=True)`
- **AND** the server built with code mode on and no destructive grant
- **WHEN** sandboxed code calls `call_tool` for that tool
- **THEN** the call fails with a not-found / not-permitted error
- **AND** the tool does not appear in `search` results

#### Scenario: Operator grant includes destructive tools

- **WHEN** the server is started with `serve --code-mode-allow-destructive`
- **THEN** `destructive` tools appear in the sandbox catalog and are callable from `execute`

#### Scenario: The agent cannot self-grant

- **WHEN** sandboxed code attempts to pass any destructive-allowing argument to the `execute` tool
- **THEN** no such argument exists on `execute` and the destructive gate is unaffected

### Requirement: Non-`all` visibility tools never reach the sandbox

Tools whose `visibility` is not `"all"` (i.e. `"hidden"` or `"cli"`) SHALL NOT appear in the MCP code-mode catalog, consistent with their existing absence from the MCP surface.

#### Scenario: CLI-tier tool excluded from MCP sandbox

- **GIVEN** a tool registered with `visibility="cli"`
- **WHEN** the MCP server's sandbox catalog is queried via `search`
- **THEN** the `cli`-tier tool is absent

### Requirement: Sandboxed tool calls carry connection scope and request-scoped DI

When sandboxed code calls `call_tool(name, params)` for a connection-scoped, DI-wired tool, the framework SHALL run the same per-call dispatch path as a direct MCP call: the connections dispatch hook resolves the wire `connection` value into a typed config, and the DI container resolves request-scoped dependencies. The tool body SHALL receive its injected dependencies and SHALL observe the connection passed in `params`.

#### Scenario: Connection-scoped DI tool invoked from the sandbox

- **GIVEN** a tool `async def list_tasks(*, store: TrackerStore) -> list[Task]` whose `store` resolves from a `connection`
- **WHEN** sandboxed code runs `await call_tool("list_tasks", {"connection": "default"})`
- **THEN** the connection `"default"` is resolved to its typed config
- **AND** `store` is injected from that connection
- **AND** the call returns the tool's result

#### Scenario: Missing connection fails legibly

- **WHEN** sandboxed code calls a connection-scoped tool without a `connection` value
- **THEN** the call fails with a clear validation error naming the missing `connection` argument

### Requirement: Code execution is exposed on the CLI when the code-mode extra is installed

When the `a2kit[code-mode]` extra is installed, the CLI SHALL provide a global `code` subcommand that accepts Python source (as an argument, via `--file`, or via stdin) and runs it through the same sandbox and the same capability gate as the MCP `execute` tool, with `call_tool(name, params)` in scope. When the extra is absent, the CLI SHALL NOT register the `code` subcommand — a lean install carries no sandbox dependency and advertises no command it cannot run.

#### Scenario: Run code from the CLI

- **WHEN** the `a2kit[code-mode]` extra is installed
- **AND** the operator runs the `code` subcommand with Python source that calls `call_tool`
- **THEN** the code runs in the sandbox and its return value is printed
- **AND** the destructive and visibility gates apply identically to the MCP surface

#### Scenario: Lean install omits the subcommand

- **WHEN** the `a2kit[code-mode]` extra is not installed
- **THEN** the `code` subcommand is absent from the CLI and from `--help`

### Requirement: Code execution is never exposed on the REST surface

The REST surface SHALL NOT expose code execution: no `execute` tool, no code-execution endpoint, and no discovery meta-tools. This requirement binds the future REST surface change.

#### Scenario: REST surface omits code execution

- **WHEN** the REST surface is generated for an app with code mode on
- **THEN** no route, endpoint, or operation corresponding to `execute` or to code execution exists

### Requirement: `pydantic-monty` and FastMCP `experimental` are lazy optional dependencies

The Monty sandbox runtime and FastMCP's `experimental` `CodeMode` SHALL be imported only from `a2kit.packages.codemode`, and only on the `build_mcp_server` / `serve` / `code`-subcommand path. `import a2kit` SHALL NOT import either. The runtime SHALL be installable via an `a2kit[code-mode]` optional-dependency extra.

#### Scenario: Cold-start import stays clean

- **WHEN** `import a2kit` runs
- **THEN** neither `pydantic_monty` nor FastMCP's `experimental` `CodeMode` module is imported

#### Scenario: Missing runtime fails with a migration hint

- **GIVEN** code mode is enabled
- **AND** `pydantic-monty` is not installed
- **WHEN** the server attempts to install the code-mode transform
- **THEN** the framework raises with a message naming the `a2kit[code-mode]` extra as the fix

### Requirement: Code-execution load timing — eager for MCP, deferred for CLI

The code-execution machinery (`a2kit.packages.codemode`, FastMCP's `experimental` `CodeMode`, and the `pydantic-monty` runtime) SHALL load at different times depending on the mode:

- **MCP mode.** When an MCP server is built with code mode on, the `A2kitCodeMode` transform SHALL be installed during `build_mcp_server` — the surface is ready as soon as the server is built, with no further deferral.
- **CLI mode.** Building the CLI and running any command other than `code` SHALL import none of `a2kit.packages.codemode`, `fastmcp`, or `pydantic-monty`. The machinery SHALL be imported only when the `code` subcommand is actually invoked. A non-importing `find_spec` check at CLI-build time (deciding whether to register `code`) is permitted — it locates the extra without loading it.

#### Scenario: MCP server has code mode ready at build time

- **WHEN** `build_mcp_server(app, code_mode=True)` returns
- **THEN** the `A2kitCodeMode` transform is already installed and `execute` is callable with no further setup

#### Scenario: CLI startup imports nothing code-execution-related

- **WHEN** the CLI is built and a command other than `code` runs (e.g. `--help`)
- **THEN** `a2kit.packages.codemode`, `fastmcp`, and `pydantic_monty` are all absent from `sys.modules`

#### Scenario: the `code` subcommand loads the machinery on invocation

- **WHEN** the `code` subcommand is invoked
- **THEN** the code-execution machinery is imported at that point and the sandbox runs

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

