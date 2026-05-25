## ADDED Requirements

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
