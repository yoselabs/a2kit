## MODIFIED Requirements

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

The system SHALL forward `title=` to MCP `ToolAnnotations.title` while keeping the tool's `name` (derived from the method name) as the protocol identifier. The public verb decorators SHALL NOT accept a `name=` kwarg; the tool name SHALL derive from `fn.__name__`.

#### Scenario: title carried alongside auto-derived name

- **WHEN** a Router method `async def fetch(...) -> FetchResponse` is decorated `@a2kit.read(title="Fetch Web Page")`
- **THEN** the MCP registration has `name="fetch"` (or kebab/dotted form per framework convention) and `ToolAnnotations(title="Fetch Web Page")`
