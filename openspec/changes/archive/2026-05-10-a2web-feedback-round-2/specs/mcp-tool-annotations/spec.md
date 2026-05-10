## ADDED Requirements

### Requirement: MCP tool annotations on verb decorators

The system SHALL accept MCP `ToolAnnotations` kwargs on `@a2kit.read`, `@a2kit.write`, and `@a2kit.tool`, forwarding them to the FastMCP server registration.

#### Scenario: read tool opts into idempotent and open-world hints

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True, open_world=True, title="Fetch")`
- **THEN** the resulting MCP tool registration carries `ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=True, title="Fetch")`

#### Scenario: write tool defaults to destructive

- **WHEN** a tool is decorated `@a2kit.write()` with no annotation kwargs
- **THEN** the resulting MCP registration carries `ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)`

### Requirement: Conservative defaults

The system SHALL apply conservative defaults for annotations not explicitly set by the consumer.

#### Scenario: openWorldHint defaults False

- **WHEN** a tool is decorated `@a2kit.read()` without `open_world=`
- **THEN** the registration carries `openWorldHint=False`

#### Scenario: idempotentHint defaults False

- **WHEN** a tool is decorated `@a2kit.read()` without `idempotent=`
- **THEN** the registration carries `idempotentHint=False`

### Requirement: Decorator validates annotation/verb fit

The system SHALL reject incompatible annotation kwargs at decoration time with a clear `TypeError`.

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the offending kwarg and the verb

### Requirement: Title is independent of tool name

The system SHALL forward `title=` to MCP `ToolAnnotations.title` while keeping the tool's `name` (e.g. `web.fetch`) as the protocol identifier.

#### Scenario: title and name carried separately

- **WHEN** a tool is decorated `@a2kit.read(name="web.fetch", title="Fetch Web Page")`
- **THEN** the MCP registration has `name="web.fetch"` and `ToolAnnotations(title="Fetch Web Page")`
