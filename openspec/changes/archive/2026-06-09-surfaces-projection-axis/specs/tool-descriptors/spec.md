## MODIFIED Requirements

### Requirement: `ToolDescriptor` carries projected tool shape

`ToolDescriptor` SHALL expose, in addition to `{name, router, fn, return_type, format_hint, encoding_plan, verb, surfaces, authorize}`, the following projected fields:

- `ctx_param_name: str | None` — name of the `ToolContext`-typed parameter on the tool function, or `None` if absent.
- `timeout: float | None` — per-tool timeout in seconds, projected from `A2KitMeta.extras.timeout_seconds`.
- `annotations_view: Mapping[str, Any]` — immutable view of `A2KitMeta.annotations_as_dict()` (no `mcp.types` import side effect on read).
- `metadata_view: Mapping[str, Any]` — immutable flattened view of `A2KitMeta` (verb, tags, context_param_name, extras as dict).
- `lazy_param_names: frozenset[str] | None` — parameter names whose annotation is `Lazy[T]`. `None` until descriptor materialization is moved to `runtime.build(app)`.
- `wire_param_names: frozenset[str] | None` — parameter names NOT resolved by the container and not `Lazy[T]` and not the ctx parameter. `None` until descriptor materialization is moved to `runtime.build(app)`.

The former `expose: tuple[str, ...]` field SHALL be removed and replaced by `surfaces: Mapping[str, Literal["absent", "listed", "unlisted"]]` — the resolved projection matrix (one entry per registered surface, see capability `surfaces-projection`). Surfaces SHALL read placement and advertisement from `descriptor.surfaces` only; no descriptor field SHALL carry the retired `expose` tuple or `visibility` string.

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

#### Scenario: descriptor carries the resolved surfaces matrix

- **GIVEN** a verb decorated `@a2kit.read(surfaces=("mcp", "cli"))` with registered surfaces `mcp`, `api`, `cli`
- **WHEN** `app.tools()[0].surfaces` is read
- **THEN** the mapping is `{"mcp": "listed", "api": "absent", "cli": "listed"}`
- **AND** the mapping is immutable (assigning a key raises `TypeError`)
- **AND** the descriptor exposes no `expose` attribute
