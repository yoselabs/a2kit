## MODIFIED Requirements

### Requirement: MCP tool annotations on verb decorators

The system SHALL accept MCP `ToolAnnotations` kwargs on `@a2kit.read`, `@a2kit.write`, and `@a2kit.list_`, forwarding them to the FastMCP server registration. The bare `@a2kit.tool` verb does not exist (removed in v0.33); the annotation-accepting verbs are `read`, `write`, and `list_`.

#### Scenario: read tool opts into idempotent and open-world hints

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True, open_world=True, title="Fetch")`
- **THEN** the resulting MCP tool registration carries `ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=True, title="Fetch")`

#### Scenario: write tool defaults to destructive

- **WHEN** a tool is decorated `@a2kit.write()` with no annotation kwargs
- **THEN** the resulting MCP registration carries `ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)`

### Requirement: Title is independent of tool name

The system SHALL forward `title=` to MCP `ToolAnnotations.title` while keeping the tool's `name` (derived from the method name) as the protocol identifier. The public verb decorators (`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`) SHALL NOT accept a `name=` kwarg; the tool name SHALL derive from `fn.__name__`.

#### Scenario: title carried alongside auto-derived name

- **WHEN** a Router method `async def fetch(...) -> FetchResponse` is decorated `@a2kit.read(title="Fetch Web Page")`
- **THEN** the MCP registration has `name="fetch"` (or kebab/dotted form per framework convention) and `ToolAnnotations(title="Fetch Web Page")`
