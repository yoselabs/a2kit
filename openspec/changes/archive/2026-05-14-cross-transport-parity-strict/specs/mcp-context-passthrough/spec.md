# mcp-context-passthrough — cross-transport-parity-strict delta

## ADDED Requirements

### Requirement: Unknown kwargs are rejected at both transport boundaries

The framework SHALL reject any kwarg that is not declared on the tool
signature at both the MCP transport boundary and the CLI runtime
dispatcher. Behaviour:

- **MCP transport** (`fastmcp.Client` → `build_mcp_server(app)`):
  unknown kwargs surface as a `ToolError(json)` whose decoded envelope
  carries `class: "TypeError"` and `message` naming the unexpected
  parameter(s).
- **CLI runtime dispatcher** (`_invoke_tool_in_process` and any
  caller of it that bypasses Typer's flag-parsing layer): unknown
  kwargs raise `TypeError` directly with the same message shape.
- **CLI Typer surface** (`<app> tasks <name> --known --unknown=...`):
  unknown CLI flags are rejected by Typer with `BadParameter`. This
  is upstream of the framework and continues to behave as today.

The contract is "both transport boundaries fail loudly on unknown
kwargs"; the consumer's choice of programmatic surface (`TestClient`,
direct `_invoke_tool_in_process`, real `fastmcp.Client`) does not
change the rejection semantics — only the error envelope shape.

#### Scenario: FastMCP rejects unknown kwarg over real transport

- **GIVEN** a tool declared as `async def t(*, msg: str) -> dict`
- **WHEN** the test calls `await c.call_tool("t", {"msg": "x", "extra": "y"})` over `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the client receives a `ToolError` whose `json.loads(str(exc))` payload has `class == "TypeError"` and `message` references `"extra"`

#### Scenario: CLI runtime dispatcher rejects unknown kwarg

- **GIVEN** the same tool, called via `_invoke_tool_in_process(t.fn, {"msg": "x", "extra": "y"}, ...)`
- **WHEN** the call is awaited
- **THEN** `TypeError` is raised before `fn(**call_kwargs)` executes; the message references `"extra"`

#### Scenario: TestClient surfaces the same envelope shape as production MCP

- **GIVEN** the same tool, called via `async with a2kit.testing.client(app) as c: await c.invoke("t", msg="x", extra="y")`
- **WHEN** the call is awaited
- **THEN** `fastmcp.exceptions.ToolError` is raised; `json.loads(str(exc))["class"] == "TypeError"`

#### Scenario: Both transports produce the same class identity

- **GIVEN** identical calls to a tool with an undeclared kwarg over MCP and via the runtime dispatcher
- **THEN** both error paths surface a `TypeError` (directly, or wrapped in a `ToolError` envelope whose decoded `class` is `"TypeError"`); the consumer can write a single matcher that handles both
