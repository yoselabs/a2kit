# runtime-tool-selection Specification

## Purpose
TBD - created by archiving change a2web-handoff-prep. Update Purpose after archive.
## Requirements
### Requirement: Runtime tool-subset selection via env var and CLI flag

a2kit SHALL accept a runtime tool-subset selector that filters the
descriptor set before MCP server registration and CLI subcommand
generation. The selector SHALL be sourced from two channels:

- Environment variable: `A2KIT_TOOLS` containing a comma-separated list
  of tool names (e.g. `A2KIT_TOOLS=ask,refresh`)
- CLI flag: `--tools=<comma-list>` on `serve` and on the top-level
  CLI invocation

When both channels are populated, the **intersection** SHALL apply
(the more restrictive set wins). When neither is populated, all
compile-time-visible tools are exposed (current behavior).

The selector SHALL be a SUBSET filter only — it CANNOT re-enable tools
filtered out at compile time by `visibility="hidden"`.

Unknown tool names in the selector SHALL fail closed with a clear
error that names the offending name(s) and lists the valid tool names
for the current App.

#### Scenario: Env-var selector restricts the MCP surface

- **GIVEN** an `App` with three `@a2kit.read()` tools `ask`, `refresh`, `fetch_raw`
- **AND** `A2KIT_TOOLS=ask,refresh` is set
- **WHEN** `build_mcp_server(app)` runs
- **THEN** the FastMCP server registers only `ask` and `refresh`
- **AND** `fetch_raw` is not registered

#### Scenario: CLI-flag selector restricts the CLI surface

- **GIVEN** the same `App` as above
- **AND** the process is invoked with `--tools=ask`
- **WHEN** the CLI builds
- **THEN** only the `ask` Click subcommand is registered

#### Scenario: Env and CLI intersect when both are set

- **GIVEN** `A2KIT_TOOLS=ask,refresh` AND CLI flag `--tools=ask,fetch_raw`
- **WHEN** the surface builds
- **THEN** only `ask` is exposed (intersection)

#### Scenario: Selector cannot re-enable a hidden tool

- **GIVEN** a tool registered with `visibility="hidden"`
- **AND** `A2KIT_TOOLS=<that-tool-name>` is set
- **WHEN** the surface builds
- **THEN** the hidden tool is NOT exposed
- **AND** the selector treats the hidden name as "unknown" and fails
  closed with a message listing the actually-selectable tools

#### Scenario: Unknown tool name fails closed

- **GIVEN** `A2KIT_TOOLS=ask,bogus`
- **WHEN** the surface builds
- **THEN** the build raises an error naming `bogus` as unknown
- **AND** the error message lists the valid tool names for the App
- **AND** no MCP server / CLI is built

### Requirement: Selector is consumed at compose-time, not per-request

The selector SHALL be resolved once during `build_mcp_server(app)` /
CLI build, NOT per request. Changing `A2KIT_TOOLS` after the server
is built has no effect until the next process restart.

#### Scenario: Restart required after env-var change

- **GIVEN** a running MCP server built with `A2KIT_TOOLS=ask`
- **WHEN** `A2KIT_TOOLS=ask,refresh` is set in the running process's env
- **AND** the server continues handling requests
- **THEN** only `ask` remains exposed
- **AND** a process restart is required for the new selection

