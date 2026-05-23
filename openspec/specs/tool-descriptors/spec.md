# tool-descriptors Specification

## Purpose
TBD - created by archiving change type-driven-format-routing. Update Purpose after archive.
## Requirements
### Requirement: `App.tools()` returns typed `ToolDescriptor` objects

`App` SHALL expose a single tool-introspection accessor `tools() -> list[ToolDescriptor]`. Each descriptor SHALL carry, at minimum, `name: str`, `router: Router`, `fn: Callable`, `return_type: type | None`, and `format_hint: Literal["tsv", "json", "page-tsv"]`. Descriptors SHALL be materialized inside `App.add_router(...)` (or equivalent registration path), not lazily on first access. Consumers that need bound callables SHALL derive them via `[d.fn for d in app.tools()]`.

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
- **THEN** the result is a list of the bound tool callables

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

Descriptors SHALL be built once per tool, at registration time, and `App.tools()` SHALL return the cached descriptors without re-running type inference.

Subsequent calls to `App.tools()` SHALL return the descriptors materialized at registration time. There is no separate `tool_descriptors()` accessor — `App.tools()` is the single tool-introspection API, and it is the call that returns cached descriptors.

#### Scenario: No work on repeated lookups

- **GIVEN** an app with N registered tools
- **WHEN** `app.tools()` is called K times
- **THEN** type inference (`typing.get_type_hints` and the inference walker) is invoked exactly N times in total — once per tool at registration

### Requirement: `ToolDescriptor` carries projected tool shape

`ToolDescriptor` SHALL expose, in addition to `{name, router, fn, return_type, format_hint, encoding_plan, verb, expose, authorize}`, the following projected fields:

- `ctx_param_name: str | None` — name of the `ToolContext`-typed parameter on the tool function, or `None` if absent.
- `timeout: float | None` — per-tool timeout in seconds, projected from `A2KitMeta.extras.timeout_seconds`.
- `annotations_view: Mapping[str, Any]` — immutable view of `A2KitMeta.annotations_as_dict()` (no `mcp.types` import side effect on read).
- `metadata_view: Mapping[str, Any]` — immutable flattened view of `A2KitMeta` (verb, tags, context_param_name, extras as dict).
- `lazy_param_names: frozenset[str] | None` — parameter names whose annotation is `Lazy[T]`. `None` until descriptor materialization is moved to `runtime.build(app)`.
- `wire_param_names: frozenset[str] | None` — parameter names NOT resolved by the container and not `Lazy[T]` and not the ctx parameter. `None` until descriptor materialization is moved to `runtime.build(app)`.

All projected fields SHALL be immutable. `Mapping` views SHALL use `types.MappingProxyType` (or equivalent) so consumers cannot mutate the underlying dict.

#### Scenario: Descriptor exposes ctx_param_name

- **GIVEN** a tool `async def fetch(self, *, ctx: ToolContext, id: str) -> Memory: ...` registered on a router
- **WHEN** `app.tools()[0]` is read
- **THEN** the descriptor's `ctx_param_name == "ctx"`

#### Scenario: Descriptor exposes timeout

- **GIVEN** a tool decorated with `@a2kit.read(timeout=5.0)`
- **WHEN** the descriptor is materialized
- **THEN** `descriptor.timeout == 5.0`

#### Scenario: annotations_view is immutable and dict-shaped

- **GIVEN** a tool decorated with `@a2kit.read(annotations=ToolAnnotations(readOnlyHint=True))`
- **WHEN** `descriptor.annotations_view` is read
- **THEN** `descriptor.annotations_view["readOnlyHint"] is True`
- **AND** attempting `descriptor.annotations_view["readOnlyHint"] = False` raises `TypeError`

#### Scenario: metadata_view exposes verb

- **GIVEN** any `@a2kit.list_(...)`-decorated tool
- **WHEN** `descriptor.metadata_view["verb"]` is read
- **THEN** the value is `"list"`

#### Scenario: container-dependent fields default to None

- **GIVEN** the current descriptor materialization runs at `add_router` (pre-`runtime.build(app)`)
- **WHEN** `descriptor.wire_param_names` and `descriptor.lazy_param_names` are read
- **THEN** both return `None` until the deferral change lands

### Requirement: Build-time descriptor re-materialization populates container-dependent fields

`runtime.build(app)` SHALL re-materialise every projection-tool `ToolDescriptor` against the runtime container, populating `wire_param_names` and `lazy_param_names`. The resulting descriptors SHALL be stored on the `AppRuntime` and exposed via `AppRuntime.descriptor_for(name)` and `AppRuntime.descriptors()`.

Pre-build descriptor access (`App.tools()`) continues to return descriptors as built at `add_router` time — their container-dependent fields stay `None`. Substrate adapters SHALL read from the `AppRuntime` surface, not `App.tools()`.

#### Scenario: build re-materialises with container

- **GIVEN** an `App` with a provider `app.provide(Database)` and a router whose tool takes `db: Database` and `id: str`
- **WHEN** `runtime = build(app)` runs
- **THEN** `runtime.descriptor_for("fetch").wire_param_names == frozenset({"id"})`
- **AND** `"db"` is NOT in `wire_param_names`

#### Scenario: pre-build descriptor keeps sentinel fields

- **GIVEN** the same `App` before `build()`
- **WHEN** `app.tools()[0]` is read
- **THEN** `descriptor.wire_param_names is None` and `descriptor.lazy_param_names is None`

#### Scenario: Lazy[T] params classified as lazy, not wire

- **GIVEN** a tool `async def warm(self, *, cache: Lazy[Cache]) -> None: ...`
- **WHEN** `build(app)` materialises runtime descriptors
- **THEN** `runtime.descriptor_for("warm").lazy_param_names == frozenset({"cache"})`
- **AND** `"cache"` is NOT in `runtime.descriptor_for("warm").wire_param_names`


### Requirement: `ToolDescriptor` is the sole external read surface for tool meta

External code (anything outside `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`) SHALL read tool metadata via `AppRuntime.descriptor_for(name)` only. Direct access to `A2KitMeta` via `metadata._get_meta` from substrate adapters, packages, or downstream consumers is forbidden and enforced by lint rule `A2K-METADATA-PRIVATE`.

Substrate adapters MAY read the projected `ToolDescriptor._meta` field (underscore-prefixed: internal projection seam). This is the approved cutover target; importing `_get_meta` directly is still rejected by the lint rule.

The public `metadata.get_meta` / `metadata.set_meta` names SHALL remain as migration-hint raises (`AttributeError` pointing to `ToolDescriptor`); they SHALL NOT return meta.

#### Scenario: substrate adapter reads via descriptor

- **GIVEN** a substrate adapter needs the tool's `annotations` dict
- **WHEN** it accesses the data
- **THEN** it reads `runtime.descriptor_for(name).annotations_view`
- **AND** it does NOT import `_get_meta` from `a2kit.metadata`

#### Scenario: legacy public name raises migration hint

- **WHEN** code calls `from a2kit.metadata import get_meta; get_meta(fn)`
- **THEN** `AttributeError` is raised
- **AND** the message names `ToolDescriptor` and `runtime.descriptor_for` as the replacement
