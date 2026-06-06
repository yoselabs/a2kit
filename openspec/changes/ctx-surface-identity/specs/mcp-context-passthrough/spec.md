## ADDED Requirements

### Requirement: MCP and CLI dispatch stamp surface identity alongside ctx binding

The MCP and CLI dispatch paths SHALL additionally resolve the invoking
surface's identity and stamp it onto the per-call scope as they bind the
live transport context into the per-call ambient state. The MCP path
SHALL stamp `surface = "mcp"` (plus the FastMCP
`client_id` as `surface_client_id` when the live context exposes one);
the CLI runtime SHALL stamp `surface = "cli"`. The surface identity SHALL
be resolved from the dispatching path (authoritative), NOT inferred from
the runtime type of the bound `ctx`.

This is additive to the existing context binding: a tool that does not
read the surface is unaffected, and the ctx passthrough contract is
unchanged. The surface fields ride the per-call scope defined by
`surface-identity-context` (which extends the `refound-ldd-on-stdlib-logging`
`_CallScope`); this requirement only pins that the MCP/CLI bind sites are
where the identity is stamped.

#### Scenario: MCP bind stamps surface alongside ctx

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> None` dispatched via `fastmcp.Client(transport=build_mcp_server(app))`
- **WHEN** the framework binds the live `fastmcp.Context` into the per-call scope
- **THEN** the same scope carries `surface == "mcp"`
- **AND** the bound `ctx` is the live `fastmcp.Context` (the existing passthrough is unchanged)

#### Scenario: MCP bind carries the FastMCP client id

- **GIVEN** an MCP dispatch whose live `fastmcp.Context` exposes a non-None `client_id`
- **WHEN** the per-call scope is bound
- **THEN** the scope's `surface_client_id` equals that `client_id`

#### Scenario: CLI runtime stamps "cli" alongside the stub context

- **GIVEN** a tool dispatched via the CLI runtime (with a `StderrToolContext` bound)
- **WHEN** the per-call scope is bound
- **THEN** the scope carries `surface == "cli"`
- **AND** the CLI ctx-binding behaviour is otherwise unchanged

#### Scenario: surface identity is not sniffed from the ctx type

- **GIVEN** a dispatch whose bound context is a generic stub indistinguishable by type from another surface's stub
- **WHEN** the surface identity is resolved
- **THEN** it reflects the dispatching path (e.g. `"cli"`), not a guess from the ctx object's type
