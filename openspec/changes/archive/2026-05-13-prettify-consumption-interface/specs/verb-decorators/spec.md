## MODIFIED Requirements

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

## ADDED Requirements

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
