## MODIFIED Requirements

### Requirement: `install(server)` adds an OTel Middleware

`a2kit.packages.otel.install(server, ...)` SHALL register a FastMCP `Middleware` subclass that wraps every `on_call_tool` invocation in an OTel span. Signature: `install(server, *, tracer_name="a2kit", meter_name="a2kit", metrics=False)`.

#### Scenario: Span attributes from A2KitMeta

- **WHEN** a tool registered with `@a2kit.read(name="get_task", tags={"read"})` is invoked through the MCP server with the OTel middleware installed
- **THEN** the active span has these attributes, keyed by the literal OTel attribute-name strings the middleware emits:
  - the attribute named "a2kit.tool_name" with value `"get_task"`
  - the attribute named "a2kit.verb" with value `"read"`
  - the attribute named "a2kit.tags" with value `"read"` (sorted, comma-joined)
  - the attribute named "a2kit.router" with value the registered Router slug

#### Scenario: Span name shape

- **WHEN** a tool named `list_tasks` is invoked
- **THEN** the recorded span's name is `mcp.tool.list_tasks`

#### Scenario: Exception recording

- **WHEN** the wrapped tool raises an exception
- **THEN** the span's status is set to ERROR, `record_exception(exc)` is
  called, and the exception bubbles unchanged to the caller

#### Scenario: Metrics off by default

- **WHEN** a user calls `install(server)` without `metrics=True`
- **THEN** no OTel meter is created; only spans are emitted

#### Scenario: Metrics on demand

- **WHEN** a user calls `install(server, metrics=True)`
- **THEN** a counter whose OTel instrument name is the literal string "a2kit.tool.calls" increments per tool call with attribute set `{tool, verb, status}` where `status ∈ {"ok", "error"}`
