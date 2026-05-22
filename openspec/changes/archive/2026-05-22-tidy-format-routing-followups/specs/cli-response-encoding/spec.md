## MODIFIED Requirements

### Requirement: `format_response` normalizes pydantic BaseModel inputs before encoding

`format_response` SHALL convert any `pydantic.BaseModel` instance reachable from the input into a JSON-mode dump (`model_dump(mode="json")`) before passing the payload to the JSON, TSV, or page-TSV encoder. Normalization SHALL recurse into `list`, `tuple`, and `dict` containers and rewrite each `BaseModel` it finds. Other values SHALL pass through unchanged.

#### Scenario: Top-level BaseModel via JSON
- **GIVEN** a tool returns `Task(id="t1", title="x")` (a pydantic model)
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the response data is the compact JSON encoding of `raw.model_dump(mode="json")` (e.g., `{"id":"t1","title":"x"}`), not a quoted repr

#### Scenario: List of BaseModels
- **GIVEN** a tool returns `[Task(id="a"), Task(id="b")]`
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the response data is the JSON encoding of `[{"id":"a", ...}, {"id":"b", ...}]`

#### Scenario: Dict containing BaseModel values
- **GIVEN** a tool returns `{"items": [Task(id="a")], "next_cursor": None}`
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the `items` array contains plain dicts dumped from each `Task`

#### Scenario: Nested BaseModel
- **GIVEN** a tool returns `Project(tasks=[Task(id="a")])` (a model whose field is a list of models)
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the response data is the JSON encoding of the fully nested dump (`{"tasks":[{"id":"a", ...}]}`)

#### Scenario: Non-pydantic values pass through unchanged
- **GIVEN** `raw = {"a": 1, "b": [1, 2, 3]}` (no `BaseModel` anywhere)
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the response data is the compact JSON encoding of `raw`, with no normalization applied

### Requirement: Auto format selection runs against the normalized payload

When `format_hint="auto"` is passed to `format_response`, the encoder SHALL be selected via the cached `format_hint` on the calling tool's `ToolDescriptor`. `format_response` itself, when called outside of a tool dispatch context (no descriptor available), SHALL fall back to `"json"`. The accepted `format_hint` vocabulary is `"auto"`, `"json"`, `"tsv"`, and `"page-tsv"`. The previous behavior — running a `toon_or_json` heuristic to choose between a TOON and a JSON encoding — is retired; the `toon_or_json` and `encode_toon` helpers no longer exist and `"toon"` is not an accepted `format_hint` value.

#### Scenario: Auto in tool dispatch reads the descriptor
- **GIVEN** a tool whose descriptor has `format_hint="tsv"`
- **WHEN** `_invoke_tool_in_process` formats the tool's return value under `--format auto`
- **THEN** the encoder dispatched is `encode_tsv`

#### Scenario: Auto in tool dispatch for a Page-returning tool
- **GIVEN** a tool annotated `-> Page[Task]` (scalar-only `Task`) whose descriptor has `format_hint="page-tsv"`
- **WHEN** `_invoke_tool_in_process` formats the return value under `--format auto`
- **THEN** the encoder dispatched is `encode_page_tsv` (JSON envelope with embedded TSV)

#### Scenario: Auto outside dispatch context falls back to JSON
- **GIVEN** a direct call `format_response(raw, format_hint="auto")` from user code (no descriptor in scope)
- **WHEN** the call is evaluated
- **THEN** the response is JSON-encoded
