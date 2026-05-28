## ADDED Requirements

### Requirement: Return-type opt-in to empty-field pruning

A pydantic `BaseModel` used as a tool return type SHALL be able to
opt into pruning empty fields from the JSON wire payload. The opt-in
SHALL be expressed at the model level via a marker on `model_config`
(or equivalent helper) — NOT as a runtime kwarg threaded through
dispatch.

An "empty field" for this rule SHALL be defined as a value matching
one of: `None`, `""` (empty string), `[]` (empty list), `{}` (empty
dict). Other zero-valued types (`0`, `0.0`, `False`, `Decimal(0)`,
empty `frozenset`) SHALL NOT be considered empty — they carry
information.

When the marker is present, `format_response` SHALL emit JSON with
empty fields omitted. The JSON schema generated for the type SHALL
be unchanged (the schema documents the type's interface; the marker
controls the wire payload). The `outputSchema` advertised on
`tools/list` MCP responses SHALL likewise be unchanged.

Default behavior (no marker) SHALL be the current behavior:
`model_dump(mode="json")` emits all fields including empties.

#### Scenario: Marker prunes None / [] / {} / '' fields

- **GIVEN** a model with the prune-empty marker on `model_config` AND
  field values: `url="https://x"`, `byline=None`, `next_links=[]`,
  `meta={}`, `note=""`
- **WHEN** the model is serialized via `format_response`
- **THEN** the JSON payload contains only `{"url": "https://x"}`
- **AND** does NOT contain `byline`, `next_links`, `meta`, or `note`

#### Scenario: Marker preserves zero-valued non-empty fields

- **GIVEN** a model with the prune-empty marker AND field values:
  `count=0`, `enabled=False`, `price=Decimal("0")`
- **WHEN** the model is serialized
- **THEN** all three fields appear in the JSON payload

#### Scenario: Default model (no marker) emits all fields

- **GIVEN** a model WITHOUT the prune-empty marker
- **WHEN** the model is serialized via `format_response`
- **THEN** the JSON payload includes all fields, including
  `byline=null` and `next_links=[]`
- **AND** behavior matches the pre-change baseline byte-for-byte

#### Scenario: Schema advertises optional fields regardless of marker

- **GIVEN** a model with the prune-empty marker AND an optional
  `byline: str | None = None` field
- **WHEN** the tool's `outputSchema` is generated
- **THEN** the schema includes `byline` as an optional field
- **AND** the schema is identical to the schema generated without the
  marker
