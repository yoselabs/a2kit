## ADDED Requirements

### Requirement: Tool results render per a consumer profile

A tool result SHALL be rendered for a **consumer profile**, one of
`llm`, `code`, or `machine`. The `llm` profile SHALL produce the
compressed wire form (TSV / page-tsv where the encoding plan marks the
data tabular, JSON otherwise). The `code` profile SHALL produce
structured values that program code can use without re-parsing. The
`machine` profile SHALL produce JSON. A single tool, reached in
different contexts, MAY be rendered under different profiles.

#### Scenario: llm consumer compresses a tabular result

- **GIVEN** a tool whose result is a list of scalar-only records
- **WHEN** the result is rendered for the `llm` consumer
- **THEN** the wire form is TSV (or page-tsv for a `Page`)

#### Scenario: code consumer keeps structure

- **WHEN** the same result is rendered for the `code` consumer
- **THEN** it is delivered as structured values, not an encoded string

#### Scenario: machine consumer is JSON

- **WHEN** the same result is rendered for the `machine` consumer
- **THEN** the wire form is plain JSON, never TSV / page-tsv

### Requirement: The `code_mode` flag selects the consumer regime at build time

The consumer profile for a tool result SHALL be fixed at
`build_mcp_server` time by the `code_mode` flag, not chosen by
inspecting call context at runtime. When `code_mode=True`, real tools'
results SHALL be rendered for the `code` consumer (their only consumer
is the sandbox) and the `execute` output SHALL be rendered for `llm`.
When `code_mode=False`, real tools' results SHALL be rendered for
`llm`.

#### Scenario: code mode on — real tool renders for code

- **WHEN** `build_mcp_server(app, code_mode=True)` is used
- **THEN** a real tool's result reaching the sandbox is `code`-rendered
- **AND** the `execute` output is `llm`-rendered

#### Scenario: code mode off — real tool renders for llm

- **WHEN** `build_mcp_server(app, code_mode=False)` is used
- **THEN** a real tool called directly is `llm`-rendered

### Requirement: Format routing applies on the MCP surface

The MCP surface SHALL format-route tool results using the descriptor's
encoding plan, consistent with the CLI surface. A result the plan
marks tabular SHALL emit the compressed form. The MCP surface SHALL
NOT emit raw JSON for a tabular `llm`-consumer result.

#### Scenario: MCP tool with a tabular result emits compressed content

- **GIVEN** an MCP server built with `code_mode=False`
- **AND** a tool annotated `-> list[Task]` where `Task` is scalar-only
- **WHEN** the tool is called over MCP
- **THEN** the result's `content` carries TSV, not raw JSON

#### Scenario: MCP tool with a non-tabular result emits JSON

- **GIVEN** a tool annotated `-> Task` (a single record)
- **WHEN** the tool is called over MCP
- **THEN** the result is JSON

### Requirement: The compressed and structured payloads occupy distinct MCP channels

An `llm`-rendered MCP result SHALL place the compressed payload (TSV /
page-tsv) in the MCP `content` block and the structured JSON in
`structuredContent`. The two SHALL be semantically equivalent. The
wrapper SHALL return a `fastmcp.ToolResult` (FastMCP's
`tool_serializer` is deprecated).

#### Scenario: llm MCP result carries both channels

- **WHEN** an `llm`-consumer MCP result is produced for a tabular tool
- **THEN** `content` contains the compressed form
- **AND** `structuredContent` contains the equivalent JSON object

### Requirement: The encoding plan covers nested flat-array fields

`build_encoding_plan(return_type)` SHALL produce a static plan that
marks every flat-array field reachable in the return type — a
`list[T]` where `T` is a scalar-only `BaseModel` — as TSV-encoded
while the enclosing object remains JSON. The plan SHALL be computed
once per tool and SHALL call `infer_format_hint` per node. A top-level
`Page[T]` SHALL be the depth-1 case (the existing page-tsv form).
`infer_format_hint` itself SHALL be unchanged.

#### Scenario: nested flat-array field is marked tsv

- **GIVEN** `class Result(BaseModel): query: str; rows: list[Hit]`
  where `Hit` is scalar-only
- **WHEN** `build_encoding_plan(Result)` is evaluated
- **THEN** the plan marks `rows` as TSV-encoded and the envelope JSON

#### Scenario: top-level Page is the depth-1 case

- **GIVEN** a tool annotated `-> Page[Task]` where `Task` is scalar-only
- **WHEN** the plan is built and applied
- **THEN** the wire form is the existing page-tsv hybrid

#### Scenario: deeply nested non-tabular structure stays JSON

- **GIVEN** a return type with no scalar-only-model array anywhere
- **WHEN** `build_encoding_plan` is evaluated
- **THEN** the plan marks the whole result JSON

### Requirement: The `execute` output is rendered by value-driven inference

The `execute` tool's dynamically-typed return value SHALL be rendered
for the `llm` consumer by **value-driven** inference, since it has no
static return annotation. The renderer SHALL sample the head of the
top-level value rather than traverse it fully, and when the value is a
list of uniform flat records SHALL encode TSV, otherwise JSON. If TSV
encoding raises, the renderer SHALL fall back to JSON.

#### Scenario: flat list of records from execute is TSV

- **WHEN** sandboxed code returns a list of uniform flat dicts
- **THEN** the `execute` output is rendered as TSV

#### Scenario: nested result from execute is JSON

- **WHEN** sandboxed code returns a nested or non-uniform structure
- **THEN** the `execute` output is rendered as JSON

#### Scenario: TSV encoding failure falls back to JSON

- **WHEN** value-driven inference selects TSV but encoding raises
- **THEN** the renderer falls back to JSON rather than failing the call

### Requirement: Code execution is never compressed on the REST surface

The REST surface SHALL render results for the `machine` consumer —
plain JSON, never TSV / page-tsv — and SHALL NOT expose code
execution. This requirement binds the future REST surface change.

#### Scenario: REST result is JSON

- **WHEN** a tool result is rendered for the REST (`machine`) consumer
- **THEN** the wire form is plain JSON regardless of the encoding plan

#### Scenario: REST omits code execution

- **WHEN** the REST surface is generated for an app with code mode on
- **THEN** no `execute` operation or code-execution endpoint exists
