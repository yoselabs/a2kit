# verb-decorators — list-verb-parameter-parity delta

## MODIFIED Requirements

### Requirement: `@a2kit.list_(...)` consolidates list-view settings

`@a2kit.list_(*default_fields: str, page_size: int | None = None, selectable_fields: tuple[str, ...] | None = None, name: str | None = None, reports: type | None = None, visibility: Literal["hidden","cli","all"] | None = None, idempotent: bool = False, open_world: bool = False, title: str | None = None)` SHALL accept the same semantic-flag and routing kwargs as the other three verb decorators (`read`, `write`, `tool`), in addition to its list-shape-specific kwargs (`*default_fields`, `page_size`, `selectable_fields`).

`destructive=` SHALL NOT be accepted on `@a2kit.list_` (list is a read shape; matches the `@a2kit.read` contract — passing `destructive=True` raises `TypeError`).

#### Scenario: `title=` and `idempotent=` propagate to ToolAnnotations
- **WHEN** a tool is decorated `@a2kit.list_("id", title="Projects", idempotent=True)`
- **THEN** `meta.annotations.title == "Projects"`
- **AND** `meta.annotations.idempotentHint is True`
- **AND** `meta.annotations.readOnlyHint is True`

#### Scenario: `visibility=` is honored
- **WHEN** a tool is decorated `@a2kit.list_("id", visibility="cli")`
- **THEN** `meta.extras.visibility == "cli"`

#### Scenario: `destructive=True` is rejected
- **WHEN** a tool is decorated `@a2kit.list_("id", destructive=True)`
- **THEN** `TypeError` is raised (list is read-shaped)
