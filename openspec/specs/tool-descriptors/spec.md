# tool-descriptors Specification

## Purpose
TBD - created by archiving change type-driven-format-routing. Update Purpose after archive.
## Requirements
### Requirement: `App.tool_descriptors()` returns typed `ToolDescriptor` objects

`App` SHALL expose `tool_descriptors() -> list[ToolDescriptor]`. Each descriptor SHALL carry, at minimum, `name: str`, `router: Router`, `fn: Callable`, `return_type: type | None`, and `format_hint: Literal["tsv", "json", "page-tsv"]`. Descriptors SHALL be materialized inside `App.add_router(...)` (or equivalent registration path), not lazily on first access. `App.tools()` SHALL continue to return the bound callables for back-compat.

#### Scenario: Descriptor for a typed tool
- **GIVEN** a router with `async def list_tasks(self, *, store: TrackerStore) -> list[Task]` where `Task` is a scalar-only `BaseModel`
- **WHEN** the router is added to an app and `app.tool_descriptors()` is called
- **THEN** the returned list contains a descriptor with `name="list_tasks"`, `return_type` resolved to `list[Task]`, and `format_hint="tsv"`

#### Scenario: Descriptor for an untyped tool
- **GIVEN** a router with a tool that has no return annotation
- **WHEN** `app.tool_descriptors()` is called
- **THEN** the descriptor's `return_type` is `None` and `format_hint` is `"json"`

#### Scenario: `tools()` back-compat
- **GIVEN** any app with at least one router
- **WHEN** `app.tools()` is called
- **THEN** it returns a list of bound callables (the same shape as before this change), so existing introspection code continues to work

### Requirement: Forward references resolve at descriptor materialization

`ToolDescriptor.return_type` SHALL be the resolved type, not a string. The descriptor materializer SHALL call `typing.get_type_hints(fn, include_extras=True)` with the function's defining-module globals so that `from __future__ import annotations` and string-quoted annotations (`"list[Task]"`) are resolved.

#### Scenario: Forward-ref resolves cleanly
- **GIVEN** a tool annotated `def get_task(...) -> "Task"` with `from __future__ import annotations` at the top of its module
- **WHEN** the router is added to an app
- **THEN** the descriptor's `return_type` is the actual `Task` class (not the string `"Task"`)

#### Scenario: Unresolvable forward-ref falls back to JSON
- **GIVEN** a tool annotation that cannot be resolved at descriptor time (e.g., a name introduced later or a typo)
- **WHEN** the router is added to an app
- **THEN** descriptor materialization SHALL emit a one-time warning, set `return_type=None`, and set `format_hint="json"` — the app SHALL build successfully

### Requirement: Descriptor build is one-shot

Descriptors SHALL be built once per tool, at registration time. Subsequent calls to `app.tool_descriptors()` SHALL return cached descriptors without re-running type inference.

#### Scenario: No work on repeated lookups
- **GIVEN** an app with N registered tools
- **WHEN** `app.tool_descriptors()` is called K times
- **THEN** type inference (`typing.get_type_hints` and the inference walker) is invoked exactly N times in total — once per tool at registration

