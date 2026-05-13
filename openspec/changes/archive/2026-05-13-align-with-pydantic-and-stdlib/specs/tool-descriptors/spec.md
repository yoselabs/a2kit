# tool-descriptors — align-with-pydantic-and-stdlib delta

## ADDED Requirements

### Requirement: Tool metadata extras are a typed pydantic model

`A2KitMeta` SHALL expose its open extension slot as
`extras: A2KitMetaExtras`, where `A2KitMetaExtras` is a
`pydantic.BaseModel` with named fields for every known extension.
The legacy `extra: dict[str, Any]` shape (string-keyed access via
`meta.extra["a2kit.report_type"]`) SHALL NOT be the consumer-facing
surface. Consumers SHALL read extensions by attribute
(`meta.extras.report_type`, `meta.extras.router_slug`,
`meta.extras.surfaces`, `meta.extras.list_view`,
`meta.extras.report_schema`).

The `A2KitMetaExtras` model SHALL declare
`model_config = ConfigDict(arbitrary_types_allowed=True)` so that
non-pydantic-native types (`type`, `Surface`) are accepted as field
values.

Tool descriptor materialization (`ToolDescriptor`) SHALL derive its
`return_type` and `format_hint` from `meta.extras` attribute access,
not from string-key lookup.

#### Scenario: Reading extras by attribute

- **GIVEN** a tool decorated with `@a2kit.reports(MyReport)` inside a
  router with `slug="x"`
- **WHEN** the tool's `A2KitMeta` is inspected
- **THEN** `meta.extras.report_type is MyReport` is true and
  `meta.extras.router_slug == "x"` is true

#### Scenario: Unset extras read as `None`, not `KeyError`

- **GIVEN** a tool with no `@reports` decoration
- **WHEN** `meta.extras.report_type` is read
- **THEN** the value is `None` (the field's default), never raising
  a `KeyError` as the legacy `meta.extra["a2kit.report_type"]` would

#### Scenario: Extras carry arbitrary-types-allowed values

- **WHEN** `meta.extras.surfaces` is set to a `Surface` flag-enum
  value and `meta.extras.report_type` is set to a Python `type`
- **THEN** both assignments succeed without pydantic raising
  "arbitrary types not allowed" — the model_config permits them
