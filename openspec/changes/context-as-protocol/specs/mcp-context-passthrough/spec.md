# mcp-context-passthrough Specification Delta

## MODIFIED Requirements

### Requirement: a2kit.ToolContext is a re-export of fastmcp.Context

`a2kit.ToolContext` SHALL be an a2kit-owned `@runtime_checkable` Protocol defined in `a2kit._context_protocol`, exposing the cross-transport ctx surface (log family, report_progress, request_id, client_id, elicit, state-store methods). The Protocol SHALL declare the contract; concrete implementations (fastmcp.Context, StderrToolContext, and any future transport's context class) SHALL satisfy it structurally — no subclassing required.

`a2kit.ToolContext is fastmcp.Context` SHALL evaluate to `False` at runtime (identity changes from the prior re-export). Consumer code annotating `ctx: a2kit.ToolContext` continues to work because both `fastmcp.Context` and `StderrToolContext` satisfy the Protocol structurally.

The library SHALL NOT import fastmcp at `a2kit._context_protocol` import time; bare `import a2kit` continues to leave `fastmcp` absent from `sys.modules`.

#### Scenario: Bare a2kit import does not pull fastmcp

- **WHEN** a process executes `import a2kit` and inspects `sys.modules`
- **THEN** `"fastmcp"` is not present in `sys.modules`

#### Scenario: ToolContext is a Protocol, not a fastmcp re-export

- **WHEN** a process executes `import a2kit; t = a2kit.ToolContext`
- **THEN** `t is fastmcp.Context` is `False` (after lazy-importing fastmcp for comparison)
- **AND** `t.__name__` is `"ToolContext"`
- **AND** introspection confirms `t` is a `typing.Protocol`

#### Scenario: fastmcp.Context satisfies the Protocol structurally

- **GIVEN** a process has lazy-imported `fastmcp.Context`
- **AND** an instance `real_ctx: fastmcp.Context` exists (built by the MCP transport)
- **WHEN** the consumer does `isinstance(real_ctx, a2kit.ToolContext)`
- **THEN** the result is `True`

#### Scenario: StderrToolContext satisfies the Protocol structurally

- **WHEN** the consumer does `isinstance(StderrToolContext(), a2kit.ToolContext)`
- **THEN** the result is `True`

#### Scenario: ToolContext appears in a2kit __all__

- **WHEN** a user runs `from a2kit import *`
- **THEN** `ToolContext` is bound in their namespace
- **AND** the value is the Protocol class
