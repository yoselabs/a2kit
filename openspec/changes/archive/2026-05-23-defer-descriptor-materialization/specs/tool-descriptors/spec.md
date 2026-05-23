## ADDED Requirements

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
