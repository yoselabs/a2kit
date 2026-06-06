## MODIFIED Requirements

### Requirement: `Surface` Protocol is the contract for substrate adapters

`a2kit.packages.dispatch.surface` SHALL define a `runtime_checkable` `Surface` Protocol with: `name: ClassVar[str]`, `kind: ClassVar[SurfaceKind]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`. The `kind` field SHALL be a `SurfaceKind` enum with exactly two members, `NETWORK` and `LOCAL`, distinguishing transports reachable over the network (MCP, HTTP) from process-local transports (the CLI). Substrate adapters (MCP, HTTP, CLI, future) SHALL satisfy this Protocol: `McpSurface` and `ApiSurface` declare `kind = SurfaceKind.NETWORK`; `CliSurface` declares `kind = SurfaceKind.LOCAL`. The `Substrate = Literal["fastapi", "fastmcp"]` discriminator stays unchanged in this capability; its removal lives in `remove-substrate-literal`.

#### Scenario: McpSurface, ApiSurface, and CliSurface satisfy Surface

- **WHEN** `isinstance(McpSurface(), Surface)`, `isinstance(ApiSurface(), Surface)`, and `isinstance(CliSurface(), Surface)` are evaluated
- **THEN** all three return `True`

#### Scenario: kind distinguishes network from local surfaces

- **WHEN** the `kind` ClassVar of each bundled surface is inspected
- **THEN** `McpSurface.kind` and `ApiSurface.kind` are `SurfaceKind.NETWORK`
- **AND** `CliSurface.kind` is `SurfaceKind.LOCAL`
- **AND** `SurfaceKind` has exactly the two members `NETWORK` and `LOCAL`
