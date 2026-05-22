# mcp-tool-annotations Specification

## Purpose
TBD - created by archiving change a2web-feedback-round-2. Update Purpose after archive.
## Requirements
### Requirement: MCP tool annotations on verb decorators

The system SHALL accept MCP `ToolAnnotations` kwargs on `@a2kit.read`, `@a2kit.write`, and `@a2kit.list_`, forwarding them to the FastMCP server registration. The bare `@a2kit.tool` verb does not exist (removed in v0.33); the annotation-accepting verbs are `read`, `write`, and `list_`.

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

#### Scenario: idempotentHint defaults False for write verbs

- **WHEN** a tool is decorated `@a2kit.write()` without `idempotent=`
- **THEN** the registration carries `idempotentHint=False`

#### Scenario: idempotentHint not user-settable for read verbs

- **WHEN** a tool is decorated `@a2kit.read()` (with or without other kwargs)
- **THEN** the `idempotent=` kwarg is not accepted by the decorator (raises `TypeError` if passed)
- **AND** the registered `ToolAnnotations` MAY carry any `idempotentHint` the framework chooses — agents are expected to ignore the field per MCP spec (meaningful only when `readOnlyHint=false`)

### Requirement: Decorator validates annotation/verb fit

The system SHALL reject incompatible annotation kwargs at decoration time with a clear `TypeError`. The rejection set SHALL match the MCP spec's conditional-meaningfulness rules: `destructiveHint` and `idempotentHint` are meaningful only when `readOnlyHint=false`, so their kwarg forms (`destructive=`, `idempotent=`) SHALL be rejected on read-shaped verbs (`@read`, `@list_`).

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the offending kwarg and the verb

#### Scenario: destructive on list raises

- **WHEN** a tool is decorated `@a2kit.list_("id", destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the offending kwarg and the verb

#### Scenario: idempotent on read raises

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the offending kwarg and the verb

#### Scenario: idempotent on list raises

- **WHEN** a tool is decorated `@a2kit.list_("id", idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the offending kwarg and the verb

#### Scenario: write accepts both destructive and idempotent

- **WHEN** a tool is decorated `@a2kit.write(destructive=False, idempotent=True)`
- **THEN** no error is raised
- **AND** `ToolAnnotations.destructiveHint == False` and `ToolAnnotations.idempotentHint == True`

### Requirement: Title is independent of tool name

The system SHALL forward `title=` to MCP `ToolAnnotations.title` while keeping the tool's `name` (derived from the method name) as the protocol identifier. The public verb decorators (`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`) SHALL NOT accept a `name=` kwarg; the tool name SHALL derive from `fn.__name__`.

#### Scenario: title carried alongside auto-derived name

- **WHEN** a Router method `async def fetch(...) -> FetchResponse` is decorated `@a2kit.read(title="Fetch Web Page")`
- **THEN** the MCP registration has `name="fetch"` (or kebab/dotted form per framework convention) and `ToolAnnotations(title="Fetch Web Page")`

