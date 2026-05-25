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

### Requirement: Tool results follow the single-mode wire rule

When the MCP server renders a tool result, it SHALL follow the single-mode rule defined in `error-envelope-rendering`:

- **Success cases**: `content[0].text` SHALL carry the canonical serialization (JSON for structured returns, `str(value)` for primitives, `"ok"` for `None`). `structuredContent` SHALL be omitted. `isError` SHALL be `false`.
- **Error cases**: `content[0].text` SHALL carry the human prose form. `structuredContent` SHALL carry `{"error": <envelope dict>}`. `isError` SHALL be `true`.

There SHALL NOT be a configuration knob for this behavior. The rule is fixed and the same across every tool in every app.

#### Scenario: Successful read tool emits text only

- **GIVEN** `@a2kit.read async def fetch(...) -> Annotated[Memory, Raises(NotFound)]: return Memory(id="x", text="hi")`
- **WHEN** the MCP `tools/call` request runs
- **THEN** the result has `isError: false`
- **AND** `content[0].text == json.dumps({"id":"x","text":"hi"})`
- **AND** `structuredContent` is absent from the result

#### Scenario: Tool raising NotFound emits prose + envelope

- **GIVEN** the same tool raises `NotFound(...)`
- **WHEN** the MCP `tools/call` request runs
- **THEN** the result has `isError: true`
- **AND** `content[0].text` is the prose-form rendering (kind label + message + hint)
- **AND** `structuredContent == {"error": {...envelope...}}`

### Requirement: MCP `tools/list` emits the auto-generated outputSchema

The MCP server's `tools/list` response SHALL emit each tool's `outputSchema` as computed by the framework from the tool's return annotation (per `error-envelope-rendering`'s outputSchema requirement). The `ErrorEnvelope` schema SHALL be defined exactly once in the MCP response's `components.schemas` and `$ref`'d from every tool's `outputSchema`.

#### Scenario: tools/list response carries auto-derived outputSchema

- **GIVEN** an app with one tool annotated `-> Annotated[Memory, Raises(NotFound)]`
- **WHEN** an MCP client calls `tools/list`
- **THEN** the tool's `outputSchema == {"oneOf": [{"$ref":"#/components/schemas/Memory"}, {"$ref":"#/components/schemas/ErrorEnvelope"}]}`
- **AND** `components.schemas.ErrorEnvelope` is defined exactly once in the response

### Requirement: MCP `ToolAnnotations` continue to compose with the typed-error contract

The existing `ToolAnnotations` kwargs (`title`, `readOnlyHint`, `idempotentHint`, `destructiveHint`, `openWorldHint`) on `@a2kit.read`/`@a2kit.write`/`@a2kit.list_` SHALL continue to work unchanged in semantics and compose cleanly with the typed-error contract carried via the return annotation. Annotation reading happens at a separate stage from `ToolAnnotations` kwarg reading; neither stage affects the other.

#### Scenario: read tool with annotations and Raises

- **GIVEN** `@a2kit.read(idempotent=True, open_world=True, title="Fetch")\nasync def fetch(...) -> Annotated[Memory, Raises(NotFound)]: ...`
- **WHEN** registered
- **THEN** the resulting MCP `ToolAnnotations` carries `readOnlyHint=true, idempotentHint=true, openWorldHint=true, title="Fetch"`
- **AND** the descriptor's `raises == (NotFound,)`

