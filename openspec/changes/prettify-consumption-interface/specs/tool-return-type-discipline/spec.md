## ADDED Requirements

### Requirement: `@a2kit.list_` validates collection-shaped return at decoration

The `@a2kit.list_` decorator SHALL inspect the decorated function's return annotation at decoration time. If `typing.get_origin(return_annotation)` is not in `{list, tuple, set, frozenset}`, the decorator SHALL raise `TypeError` naming the function, the actual annotation, and the expected `list[T]` shape. A missing return annotation SHALL also raise. This check runs BEFORE `_derive_selectable_fields` so the failure is loud rather than degrading to empty selectable fields.

Bare `list` (without a type parameter) SHALL be allowed but emits a one-time `RuntimeWarning` at decoration noting that selectable-field derivation will be empty.

#### Scenario: non-list return raises at decoration

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> dict: ...`
- **THEN** a `TypeError` is raised at decoration time
- **AND** the message names `f`, the annotation `dict`, and the expected `list[T]` shape

#### Scenario: missing return annotation raises

- **WHEN** `@a2kit.list_("id")` decorates a function with no return annotation
- **THEN** a `TypeError` is raised at decoration time

#### Scenario: list[T] is accepted

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> list[Task]: ...`
- **THEN** no error is raised
- **AND** selectable fields are derived from `Task`

#### Scenario: bare list warns

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> list: ...`
- **THEN** decoration succeeds
- **AND** a `RuntimeWarning` is emitted once naming the missing type parameter

#### Scenario: tuple/set/frozenset accepted

- **WHEN** `@a2kit.list_("id")` decorates a function returning `tuple[Task, ...]`, `set[Task]`, or `frozenset[Task]`
- **THEN** no error is raised
