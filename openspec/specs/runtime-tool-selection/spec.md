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

### Requirement: `surface=` selection removes the other surfaces

A `surface=` selector SHALL narrow the descriptor's source surface matrix (`extras.surfaces`), not merely the derived `expose` tuple, so that every surface builder agrees on placement. For an include set, each network surface (`mcp`/`api`) not in the include set SHALL be set to `ABSENT`; each excluded surface SHALL be set to `ABSENT`. The `cli` surface is not a `--select` target and SHALL be left unchanged. The selector SHALL also apply to synthetic `_meta.*` tools (e.g. `_meta.health`), so a selected surface actually removes the others rather than being kept alive by a framework-internal tool. A descriptor whose network surfaces all become `ABSENT` SHALL be dropped.

#### Scenario: MCP-only select drops the REST mount even with a health check

- **GIVEN** an `App` with a `@app.health_check` registration and a `@a2kit.read()` projection tool
- **WHEN** it is built with `select=["surface=mcp"]` and mounted via `build_parent_app`
- **THEN** the parent mounts `/mcp` only — `/api` is not mounted
- **AND** a `GET /api/openapi.json` against the mounted app is not served

#### Scenario: the source matrix is narrowed, not just expose

- **GIVEN** the same `App` built with `select=["surface=mcp"]`
- **WHEN** the projection tool's descriptor is inspected
- **THEN** `advertised_on(matrix_for(descriptor._meta.extras), "api")` is `False`
- **AND** `descriptor.expose` equals `("mcp",)`

#### Scenario: the synthetic `_meta.health` tool is narrowed like any other

- **GIVEN** an `App` with a `@app.health_check` registration built with `select=["surface=mcp"]`
- **WHEN** the `_meta.health` descriptor is inspected
- **THEN** its `expose` equals `("mcp",)`
- **AND** its matrix no longer advertises `api`

#### Scenario: cli matrix state is preserved under a network surface select

- **GIVEN** a projection tool LISTED on `mcp`, `api`, and `cli`
- **WHEN** it is built with `select=["surface=mcp"]`
- **THEN** its matrix still mounts `cli` (a `--select surface=` narrow touches only the network surfaces)

#### Scenario: api-only select is the symmetric case

- **GIVEN** an `App` with a `@app.health_check` registration and a projection tool
- **WHEN** it is built with `select=["surface=api"]` and mounted via `build_parent_app`
- **THEN** the parent mounts `/api` only — `/mcp` is not mounted

