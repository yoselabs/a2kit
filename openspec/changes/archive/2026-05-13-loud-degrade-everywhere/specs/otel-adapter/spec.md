## MODIFIED Requirements

### Requirement: `install(server)` adds an OTel Middleware

The system SHALL register a FastMCP `Middleware` subclass via `a2kit.packages.otel.install(server, *, tracer_name="a2kit", meter_name="a2kit", metrics=False)` that wraps every `on_call_tool` invocation in an OTel span. The middleware SHALL look up tool metadata (`A2KitMeta` round-tripped through the FastMCP tool's `meta["a2kit"]` payload) via `server.get_tool(tool_name)` to derive span attributes. When that lookup raises an exception, the middleware SHALL NOT propagate the exception and SHALL NOT abort span construction; it SHALL proceed with empty `a2kit.*` attributes (only `a2kit.tool_name` is set, since that value is taken from `params.name` rather than from the metadata lookup) and SHALL emit exactly one WARN-level log line per `tool_name` per process, identifying the tool and the underlying exception. The dedupe set SHALL be module-local to `packages/otel/middleware.py`.

#### Scenario: Span attributes from A2KitMeta
- **WHEN** a tool registered with `@a2kit.read(name="get_task", tags={"read"})` is invoked through the MCP server with the OTel middleware installed
- **THEN** the active span has attributes:
  - `a2kit.tool_name = "get_task"`
  - `a2kit.verb = "read"`
  - `a2kit.tags = "read"` (sorted, comma-joined)
  - `a2kit.router = "<router-slug>"` (the registered Router slug)

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
- **THEN** a counter named `a2kit.tool.calls` increments per tool call with
  attribute set `{tool, verb, status}` where `status ∈ {"ok", "error"}`

#### Scenario: Metadata lookup failure degrades span attributes with one warn-once log

- **GIVEN** an MCP server with the OTel middleware installed and a registered tool named `broken_tool`
- **AND** `server.get_tool("broken_tool")` raises an exception (e.g. due to a transient FastMCP registry error)
- **WHEN** the middleware processes a `call_tool` for `broken_tool`
- **THEN** the active span SHALL be created with `a2kit.tool_name = "broken_tool"` only; `a2kit.verb`, `a2kit.router`, `a2kit.tags`, and any other metadata-derived attributes SHALL be absent
- **AND** the middleware SHALL NOT raise; the wrapped tool call proceeds normally
- **AND** exactly one WARN-level log line is emitted by `packages/otel/middleware.py`, naming `broken_tool` and the underlying exception
- **AND** a second invocation of `broken_tool` in the same process SHALL NOT emit a second log line (dedupe by `tool_name` via a module-local `_WARN_ONCE: set[str]`)

#### Scenario: Metadata lookup failure for a different tool emits its own log line

- **GIVEN** the same server, after `broken_tool` has already emitted its one WARN
- **WHEN** a different tool `other_broken_tool` is invoked and its `server.get_tool` lookup also raises
- **THEN** one WARN-level log line is emitted naming `other_broken_tool` (different `tool_name`, so a new dedupe entry)
- **AND** subsequent invocations of `other_broken_tool` in the same process SHALL NOT emit a second line
