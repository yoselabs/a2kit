## ADDED Requirements

### Requirement: `McpSurface` satisfies the `Surface` Protocol and owns Context passthrough

`McpSurface` SHALL subclass `DecoratorSurface[McpRegistration]` and SHALL set `name = "mcp"`, `reserved_types = frozenset({Context})`, `substrate_dep_markers = frozenset()`. The body of `build_mcp_server` SHALL move into `McpSurface.bind`. `McpSurface.install_di_bridge` SHALL wire FastMCP `Context.principal` extraction into the call scope (delegating to the mechanism in `principal-propagation`). `packages/mcp/__init__.py` SHALL register `McpSurface()` with `SURFACE_REGISTRY` at lazy load.

#### Scenario: Context detection survives the Surface migration

- **GIVEN** an MCP tool `async def fetch(*, ctx: Context, id: str) -> Memory: ...`
- **WHEN** the tool is invoked via FastMCP
- **THEN** the `ctx` parameter is filled by FastMCP's Context (via `Surface.reserved_types`)
- **AND** the wire schema for the tool exposes `id` but not `ctx`
