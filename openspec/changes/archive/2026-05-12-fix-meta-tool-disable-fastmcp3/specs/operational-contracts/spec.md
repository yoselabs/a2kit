# operational-contracts — fix-meta-tool-disable-fastmcp3 delta

## ADDED Requirements

### Requirement: The `_meta.*` tool namespace is closed and split per transport

The system SHALL reserve the `_meta.*` tool-name prefix for
framework-internal protocol tools and SHALL surface those tools
differently per transport.

On the MCP transport:

- `_meta.*` tools SHALL be excluded from the default `list_tools`
  result.
- `_meta.*` tools SHALL NOT be callable via the MCP `call_tool`
  wire. An MCP client invoking `_meta.health` by exact name
  receives a `NotFoundError`. The CLI is the supported surface
  for operators who need to invoke them.

On the CLI transport:

- `_meta.*` tools SHALL appear in `<app> --help` output under a
  `_meta` subcommand group, discoverable to human operators.

At registration time (whether via decoration or via
`build_mcp_server`'s tool loop):

- A user tool whose resolved name starts with `_meta.` and which
  was not registered through a2kit's own internal builders SHALL
  be rejected with a typed error (`ValueError`) naming the reserved
  namespace.

#### Scenario: MCP default list_tools omits _meta tools

- **WHEN** an MCP client calls `list_tools` against an app
  constructed with `health_tool=True` and no opt-in flag
- **THEN** the returned tool list does not include any tool whose
  name starts with `_meta.`

#### Scenario: MCP direct invocation by name is rejected for _meta tools

- **WHEN** an MCP client calls `_meta.health` by exact name on
  an app constructed with `health_tool=True`
- **THEN** the dispatcher raises `NotFoundError` (or the
  FastMCP-3 equivalent) and the tool body is not executed

#### Scenario: CLI surfaces _meta tools under a discoverable group

- **WHEN** a user runs `<app> --help` on an app with at least one
  `_meta.*` tool registered
- **THEN** the help output documents a `_meta` subcommand group
  whose entries include each `_meta.*` tool

#### Scenario: User registration with reserved name is rejected at build time

- **WHEN** a tool with a `_meta.*` name is presented to
  `build_mcp_server` without the a2kit-internal sentinel in its
  metadata
- **THEN** `build_mcp_server` raises `ValueError` naming the
  reserved namespace and pointing at the documented contract
