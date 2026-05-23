## ADDED Requirements

### Requirement: Descriptors materialise at `App.build()`, not `App.add_router`

`ToolDescriptor` instances SHALL be materialised inside `App.build()` (or its finishing step that produces the `AppRuntime`), after the DI container is finalised. `App.add_router(...)` SHALL store the router without computing descriptors. This guarantees the container is available when wire/lazy classification runs.

#### Scenario: add_router does not materialise descriptors

- **GIVEN** a fresh `App("t")`
- **WHEN** `app.add_router(MyRouter())` runs
- **THEN** no `ToolDescriptor` is constructed
- **AND** `app.tools()` raises `RuntimeError("App.tools() requires App.build()")`

#### Scenario: build materialises descriptors with container in scope

- **GIVEN** an `App` with a router whose tool takes `db: Database` (container-provided) and `id: str`
- **WHEN** `app.build()` runs
- **THEN** `runtime.descriptor_for("fetch").wire_param_names == frozenset({"id"})`
- **AND** `"db"` is NOT in `wire_param_names`

### Requirement: Container-dependent descriptor fields finalised

`wire_param_names` and `lazy_param_names` SHALL be populated (not `None`) on every descriptor produced by `App.build()`. The defaults from [[extend-descriptor-fields]] only apply when descriptors are accessed before build, which is now disallowed.

- `wire_param_names = frozenset(wire_input_params(fn, container)[0].keys())`
- `lazy_param_names = frozenset(name for name, ann in resolve_hints(fn).items() if lazy_inner_type(ann) is not None)`

#### Scenario: Lazy[T] params classified as lazy, not wire

- **GIVEN** a tool `async def warm(self, *, cache: Lazy[Cache]) -> None: ...`
- **WHEN** `app.build()` materialises descriptors
- **THEN** `descriptor.lazy_param_names == frozenset({"cache"})`
- **AND** `"cache"` is NOT in `descriptor.wire_param_names`
