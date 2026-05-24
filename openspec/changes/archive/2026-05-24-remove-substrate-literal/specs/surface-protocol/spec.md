## ADDED Requirements

### Requirement: `build_parent_app` SHALL mount surfaces via registry walk

`packages/serve.py:build_parent_app` SHALL walk `SURFACE_REGISTRY` instead of hardcoded `_has_api_registrations` / `_has_mcp_registrations` branches. For each surface with non-empty registrations on the active runtime, it SHALL call `surface.bind(runtime)` and mount the result at `/{surface.name}`. The hardcoded `_has_*` helpers SHALL be deleted.

The runtime currently surfaces only the bundled `api` / `mcp` accumulators (`runtime.api_surface` / `runtime.mcp_surface`), so registry-walk inspection of "has this surface any registrations?" still hits a bundled-only branch inside the helper. Third-party surface accumulators on the runtime are a follow-up; the registry-walk + mount path is already in place.

#### Scenario: Bundled surfaces mount via registry walk

- **GIVEN** a runtime with one `@a2kit.read` tool (default `expose=("mcp", "api")`)
- **WHEN** `build_parent_app(runtime)` runs
- **THEN** the resulting parent app mounts both `/mcp` and `/api`
- **AND** the mounts come from walking `SURFACE_REGISTRY` (no hardcoded `_has_*` branches remain in `serve.py`)

### Requirement: `ToolDescriptor.expose` SHALL widen to `tuple[str, ...]`

`ToolDescriptor.expose` SHALL be `tuple[str, ...]` (not `tuple[Literal["mcp", "api"], ...]`). The `Literal["mcp", "api"]` typing SHALL be removed from the public descriptor surface. Decoration-time validation in `a2kit._verbs._validate_expose` SHALL reject unknown surface names with a `ValueError` naming the bundled set `{"mcp", "api"}`.

Registry-driven open-set validation against `SURFACE_REGISTRY.names()` is a follow-up: `_verbs` lives in the authoring layer (L2) and `SURFACE_REGISTRY` lives in dispatch (L4); reading the registry from L2 would violate `A2K-LAYER`. A future change will either relocate the registry to a lower layer or move expose validation into the runtime layer.

#### Scenario: Unknown expose name rejected at decoration

- **GIVEN** `@a2kit.read(expose=("mcp", "graphql"))`
- **WHEN** the decorator runs
- **THEN** a `ValueError` names `"graphql"` and lists the accepted set `{"mcp", "api"}`

#### Scenario: ToolDescriptor.expose type is open-set

- **WHEN** introspecting `ToolDescriptor.__annotations__["expose"]`
- **THEN** the type is `tuple[str, ...]`, not a `Literal` narrowing

### Requirement: `Substrate` Literal import SHALL raise with migration hint

`a2kit.packages.dispatch.substrate.Substrate` SHALL no longer exist. Any attempt to import or attribute-access `Substrate` from that module SHALL raise with a hint pointing to `Surface` / `SURFACE_REGISTRY`.

#### Scenario: Substrate import raises with migration hint

- **WHEN** any module evaluates `from a2kit.packages.dispatch.substrate import Substrate`
- **THEN** an `ImportError` (or attribute-access raise) fires with a message naming `Surface` as the replacement
