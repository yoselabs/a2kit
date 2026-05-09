## ADDED Requirements

### Requirement: `format_response` normalizes pydantic BaseModel inputs before encoding

`format_response` SHALL convert any `pydantic.BaseModel` instance reachable from the input into a JSON-mode dump (`model_dump(mode="json")`) before passing the payload to the JSON or TOON encoder. Normalization SHALL recurse into `list`, `tuple`, and `dict` containers and rewrite each `BaseModel` it finds. Other values SHALL pass through unchanged.

#### Scenario: Top-level BaseModel via JSON
- **GIVEN** a tool returns `Task(id="t1", title="x")` (a pydantic model)
- **WHEN** `format_response(raw, format_hint="json")` is called
- **THEN** the response data is the compact JSON encoding of `raw.model_dump(mode="json")` (e.g., `{"id":"t1","title":"x"}`), not a quoted repr

#### Scenario: Top-level BaseModel via TOON
- **GIVEN** a tool returns `Task(id="t1", title="x")`
- **WHEN** `format_response(raw, format_hint="toon")` is called
- **THEN** the response data equals `encode_toon(raw.model_dump(mode="json"))` and no `Unsupported type` warning is emitted

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

#### Scenario: Non-pydantic values are byte-identical
- **GIVEN** `raw = {"a": 1, "b": [1, 2, 3]}` (no `BaseModel` anywhere)
- **WHEN** `format_response(raw, format_hint="json")` and `format_response(raw, format_hint="toon")` are called
- **THEN** the outputs equal those of the pre-change formatter byte-for-byte

### Requirement: Auto format selection runs against the normalized payload

When `format_hint="auto"`, `toon_or_json` SHALL be evaluated against the normalized payload (post-`model_dump`), not against the raw input. A `BaseModel` whose dumped form is a dict containing list/dict values SHALL therefore select TOON.

#### Scenario: Auto picks TOON for a model with list field
- **GIVEN** a tool returns `Project(tasks=[Task(id="a"), Task(id="b")])`
- **WHEN** `format_response(raw, format_hint="auto")` is called
- **THEN** the chosen format is `"toon"` and the data equals `encode_toon(raw.model_dump(mode="json"))`

#### Scenario: Auto picks JSON for a flat model
- **GIVEN** a tool returns `Task(id="a", title="x")` (no list/dict fields)
- **WHEN** `format_response(raw, format_hint="auto")` is called
- **THEN** the chosen format is `"json"` and the data equals the compact JSON encoding of the dump
