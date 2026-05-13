# verb-decorators Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
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

Verb decorators SHALL accept the semantic-flag kwargs (`open_world`, `title`; plus `idempotent`, `destructive` on write-verbs only — see "Verb decorators reject incompatible annotation kwargs") and the routing kwarg `reports`. Verb decorators SHALL NOT accept a `tags=` kwarg (framework-derived tags `"read"`, `"write"`, `"list"` are stamped automatically). Verb decorators SHALL NOT accept a `name=` kwarg on the public surface; the tool name SHALL be derived from `fn.__name__`. The internal `_meta.health` registration MAY use a private `_read_internal` helper that exposes `name=`; that helper is not part of the public API.

#### Scenario: `tags=` kwarg is rejected

- **WHEN** a tool is decorated `@a2kit.read(tags={"custom"})`
- **THEN** Python raises `TypeError` (unexpected keyword argument)

#### Scenario: `name=` kwarg is rejected on public surface

- **WHEN** a tool is decorated `@a2kit.read(name="custom-name")`
- **THEN** Python raises `TypeError` (unexpected keyword argument)
- **AND** the error message points the author at renaming the method

#### Scenario: Auto-derived name from method

- **WHEN** a Router method `async def list_tasks(...) -> list[Task]` is decorated `@a2kit.list_()`
- **THEN** the resulting tool name is `"list_tasks"` (or kebab-cased equivalent per the framework convention)

#### Scenario: Auto-stamped verb tags still appear

- **WHEN** a tool is decorated `@a2kit.read()`
- **THEN** `meta.tags == frozenset({"read"})`

### Requirement: Verb decorators reject incompatible annotation kwargs

`@a2kit.read` and `@a2kit.list_` SHALL raise `TypeError` at decoration time if `destructive=` or `idempotent=` is passed. Both flags are meaningful in the MCP spec only when `readOnlyHint=false` (i.e., on write-verbs). Reads are non-destructive and idempotent by definition. The TypeError SHALL name the rejected kwarg and the verb, and SHALL suggest `@a2kit.write` as the alternative if the author intended write-like semantics.

`@a2kit.write` SHALL continue to accept `destructive=` and `idempotent=`.

The bare `@a2kit.tool` decorator SHALL be removed; authors choose `@read` / `@write` / `@list_` based on the tool's semantics.

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb

#### Scenario: idempotent on read raises

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb
- **AND** the message explains that reads are spec-idempotent by definition
- **AND** the message suggests `@a2kit.write` if a repeat-safe write was intended

#### Scenario: idempotent on list raises

- **WHEN** a tool is decorated `@a2kit.list_("id", idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb

#### Scenario: @a2kit.tool is removed

- **WHEN** consumer code references `a2kit.tool`
- **THEN** the import raises `AttributeError` with a message suggesting `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` as the replacements

#### Scenario: destructive on write still accepted

- **WHEN** a tool is decorated `@a2kit.write(destructive=False)`
- **THEN** no error is raised
- **AND** the `destructiveHint` annotation is set to `False`

#### Scenario: idempotent on write still accepted

- **WHEN** a tool is decorated `@a2kit.write(idempotent=True)`
- **THEN** no error is raised
- **AND** the `idempotentHint` annotation is set to `True`

### Requirement: Verb decorators reject mixing explicit annotations with flag kwargs

Verb decorators SHALL raise `TypeError` at decoration time when an explicit `annotations=ToolAnnotations(...)` argument is passed alongside any of the flag kwargs (`idempotent`, `open_world`, `destructive`, `title`). The two paths are mutually exclusive: either compose annotations via flag kwargs, or pass the explicit object. Silent winners are not permitted.

#### Scenario: annotations + flag kwarg raises

- **WHEN** a tool is decorated `@a2kit.write(annotations=ToolAnnotations(title="X"), idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming both `annotations` and the conflicting flag kwarg(s)
- **AND** the message instructs the author to pick one path

#### Scenario: annotations alone still accepted

- **WHEN** a tool is decorated `@a2kit.write(annotations=ToolAnnotations(title="X", idempotentHint=True))`
- **THEN** no error is raised
- **AND** the resulting annotations match the explicit object exactly

#### Scenario: flag kwargs alone still accepted

- **WHEN** a tool is decorated `@a2kit.write(idempotent=True, title="X")`
- **THEN** no error is raised
- **AND** the resulting `ToolAnnotations` carries `idempotentHint=True` and `title="X"`

### Requirement: `@a2kit.list_` validates list-shaped return annotation at decoration

The `@a2kit.list_` decorator SHALL inspect the decorated function's return annotation at decoration time. If `typing.get_origin(return_annotation)` is not in `{list, tuple, set, frozenset}`, the decorator SHALL raise `TypeError` naming the function, the actual annotation, and the expected `list[T]` shape. A missing return annotation (`None` origin) SHALL also raise. Generic `list` (without a type parameter) SHALL be allowed but emits a one-time warning at decoration that selectable-field derivation will be empty.

#### Scenario: non-list return raises

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> dict: ...`
- **THEN** a `TypeError` is raised at decoration time naming `f`, the actual annotation `dict`, and the expected `list[T]` shape

#### Scenario: missing return annotation raises

- **WHEN** `@a2kit.list_("id")` decorates a function with no return annotation
- **THEN** a `TypeError` is raised at decoration time

#### Scenario: list[T] is accepted

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> list[Task]: ...`
- **THEN** no error is raised
- **AND** selectable fields are derived from `Task`

#### Scenario: tuple/set/frozenset returns are accepted

- **WHEN** `@a2kit.list_("id")` decorates a function returning `tuple[Task, ...]` (or `set[Task]` / `frozenset[Task]`)
- **THEN** no error is raised

### Requirement: `@a2kit.list_(page_size=...)` rejects non-positive values

The `@a2kit.list_` decorator SHALL raise `ValueError` at decoration time when `page_size` is passed as a value less than or equal to zero. `page_size=None` SHALL continue to mean "no pagination."

#### Scenario: zero page_size raises

- **WHEN** `@a2kit.list_("id", page_size=0)` is applied to a tool
- **THEN** a `ValueError` is raised at decoration time naming the offending value

#### Scenario: negative page_size raises

- **WHEN** `@a2kit.list_("id", page_size=-1)` is applied to a tool
- **THEN** a `ValueError` is raised at decoration time

#### Scenario: positive page_size accepted

- **WHEN** `@a2kit.list_("id", page_size=20)` is applied to a tool
- **THEN** no error is raised
- **AND** `meta.list_view.page_size == 20`

### Requirement: Semantic flags are a locked transport-neutral vocabulary

Four decorator kwargs SHALL form a locked transport-neutral semantic
vocabulary: `idempotent`, `open_world`, `destructive`, `title`. They
MUST NOT be treated as MCP-specific escape hatches. Each flag MUST
have a meaningful read on at least two transports. Any addition to
this vocabulary MUST be captured in an ADR superseding or extending
`docs/adr/0003-semantic-flag-vocabulary.md`.

#### Scenario: Vocabulary is documented in ADR 0003
- **WHEN** a contributor reads `docs/adr/0003-semantic-flag-vocabulary.md`
- **THEN** the ADR enumerates the four flags
- **AND** lists the per-transport read for each (MCP, CLI, REST, GraphQL)
- **AND** documents the contract for adding new flags (two-transport minimum)

#### Scenario: `annotations={...}` collapse is explicitly rejected
- **WHEN** a future audit proposes collapsing the four flags into one `annotations={...}` dict
- **THEN** ADR 0003 names this collapse as the rejected alternative and points at why (would promote MCP to a privileged transport in the surface)

### Requirement: `visibility` kwarg controls transport mounting tier

Verb decorators SHALL accept a `visibility` kwarg of type
`Literal["hidden", "cli", "all"] | None` with default `None`.
`None` means "inherit from the Router's `visibility` class
attribute (default `"all"`)". Tier semantics:

- `"hidden"` — CLI-invokable but absent from `--help` listing;
  not registered on any programmatic transport (MCP / future REST /
  future GraphQL).
- `"cli"` — visible in `--help`; not registered on programmatic
  transports.
- `"all"` — registered on every transport the App exposes (default).

#### Scenario: `visibility="hidden"` hides from --help and MCP
- **GIVEN** a tool `force_unlock` decorated `@a2kit.write(visibility="hidden")`
- **WHEN** the CLI is built and `<app> --help` runs
- **THEN** `force_unlock` is absent from the listing
- **AND** `<app> ops force_unlock` still executes when invoked directly
- **AND** the MCP server does not register `force_unlock`

#### Scenario: `visibility="cli"` excludes from MCP only
- **GIVEN** a tool `login` decorated `@a2kit.write(visibility="cli")`
- **WHEN** the MCP server is built
- **THEN** `login` is not in `server.list_tools()`
- **AND** `<app> connections login --help` runs successfully on the CLI

#### Scenario: Router class attr provides default
- **GIVEN** a Router class with `visibility = "cli"` and a tool with no `visibility=` kwarg
- **WHEN** the tool is registered on an App
- **THEN** its effective `meta.extras.visibility == "cli"`

#### Scenario: Per-tool kwarg overrides Router default
- **GIVEN** a Router class with `visibility = "cli"` and a tool decorated `@a2kit.read(visibility="all")`
- **WHEN** the tool is registered on an App
- **THEN** its effective `meta.extras.visibility == "all"`

