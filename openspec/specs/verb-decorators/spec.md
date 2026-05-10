# verb-decorators Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: `@a2kit.list_(...)` consolidates list-view settings

`@a2kit.list_(*default_fields: str, page_size: int | None = None, selectable_fields: tuple[str, ...] | None = None, name: str | None = None, tags: frozenset[str] = ..., annotations: ToolAnnotations | None = None)` SHALL accept default fields as positional varargs and list-view kwargs directly. The standalone `@lists(...)` decorator and the `a2kit.packages.mcp.lists` module SHALL be removed.

#### Scenario: Positional default fields
- **WHEN** a tool is decorated `@a2kit.list_("id", "title", "status", page_size=20)`
- **THEN** the resulting `A2KitMeta.extra["a2kit.list_view"]` carries `default_fields=("id", "title", "status")` and `page_size=20`

#### Scenario: Old `@lists(...)` decorator removed
- **WHEN** lint scans the repo
- **THEN** the import path `a2kit.packages.mcp.lists` is reported as removed and any usage triggers `A2K-CORE-CLEAN` or an import error

### Requirement: `selectable_fields` is derived from return-type annotation

When `selectable_fields` is omitted, the framework SHALL derive it from the tool's return annotation: a `list[T]` return where `T` is a Pydantic `BaseModel` or `dataclass` SHALL produce `tuple(T.__pydantic_fields__)` or the dataclass field names. When `selectable_fields` is provided explicitly, the explicit value SHALL be used unchanged.

#### Scenario: Derivation from list[Model]
- **GIVEN** a tool method `async def list_tasks(...) -> list[Task]` decorated `@a2kit.list_("id", "title")`
- **WHEN** the framework collects metadata
- **THEN** `meta.extra["a2kit.list_view"].selectable_fields` equals the field names of `Task` in declaration order

#### Scenario: Explicit override
- **WHEN** the decorator is `@a2kit.list_("id", selectable_fields=("id", "title"))`
- **THEN** `selectable_fields` is `("id", "title")` even if `Task` has more fields

#### Scenario: Validation of default_fields ⊆ selectable_fields
- **WHEN** `@a2kit.list_("id", "missing")` is applied to a tool whose return type's fields do not include `"missing"`
- **THEN** lint rule reports a violation at collect time

### Requirement: Verb decorators accept MCP annotation kwargs

`@a2kit.read`, `@a2kit.write`, and `@a2kit.tool` SHALL accept the MCP-annotation kwargs `idempotent: bool`, `open_world: bool`, and `title: str | None` (and `destructive: bool` on `@write` and `@tool`), forwarding them to the constructed `ToolAnnotations`.

#### Scenario: read with all annotation kwargs

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True, open_world=True, title="Fetch")`
- **THEN** the stamped `A2KitMeta.annotations` carries `ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=True, title="Fetch")`

#### Scenario: write with destructive override

- **WHEN** a tool is decorated `@a2kit.write(destructive=False, idempotent=True, title="Mark Complete")`
- **THEN** the annotations carry `readOnlyHint=False, destructiveHint=False, idempotentHint=True, title="Mark Complete"`

### Requirement: Verb decorators reject incompatible annotation kwargs

`@a2kit.read` SHALL raise `TypeError` if `destructive=` is passed (only meaningful on `@write` / `@tool`).

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb

