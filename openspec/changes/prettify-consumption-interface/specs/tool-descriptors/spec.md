## MODIFIED Requirements

### Requirement: `App.tools()` returns typed `ToolDescriptor` objects

`App` SHALL expose a single tool-introspection accessor `tools() -> list[ToolDescriptor]`. Each descriptor SHALL carry, at minimum, `name: str`, `router: Router`, `fn: Callable`, `return_type: type | None`, and `format_hint: Literal["tsv", "json", "page-tsv"]`. Descriptors SHALL be materialized inside `App.add_router(...)` (or equivalent registration path), not lazily on first access. The legacy `App.tool_descriptors()` method SHALL be removed. Consumers that previously called `app.tools()` to obtain bound callables SHALL now derive them via `[d.fn for d in app.tools()]`.

#### Scenario: Descriptor for a typed tool

- **GIVEN** a router with `async def list_tasks(self, *, store: TrackerStore) -> list[Task]` where `Task` is a scalar-only `BaseModel`
- **WHEN** the router is added to an app and `app.tools()` is called
- **THEN** the returned list contains a descriptor with `name="list_tasks"`, `return_type` resolved to `list[Task]`, and `format_hint="tsv"`

#### Scenario: Descriptor for an untyped tool

- **GIVEN** a router with a tool that has no return annotation
- **WHEN** `app.tools()` is called
- **THEN** the descriptor's `return_type` is `None` and `format_hint` is `"json"`

#### Scenario: Callable extraction via descriptor.fn

- **GIVEN** any app with at least one router
- **WHEN** consumer code computes `callables = [d.fn for d in app.tools()]`
- **THEN** the result is a list of the bound tool callables (same shape the old `app.tools()` returned)

#### Scenario: Legacy `tool_descriptors()` removed

- **WHEN** consumer code calls `app.tool_descriptors()`
- **THEN** `AttributeError` is raised
- **AND** the error message points the consumer at `app.tools()` as the replacement
