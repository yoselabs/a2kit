## ADDED Requirements

### Requirement: `Surface` Protocol is the contract for substrate adapters

`a2kit.packages.dispatch.surface` SHALL define a `runtime_checkable` `Surface` Protocol with: `name: ClassVar[str]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`. Substrate adapters (MCP, HTTP, future) SHALL satisfy this Protocol. The `Substrate = Literal["fastapi", "fastmcp"]` discriminator SHALL be retired; surface identity SHALL flow through Surface objects instead of strings.

#### Scenario: McpSurface and ApiSurface satisfy Surface

- **WHEN** `isinstance(McpSurface(), Surface)` and `isinstance(ApiSurface(), Surface)` are evaluated
- **THEN** both return `True`

#### Scenario: `Substrate` Literal import raises with migration hint

- **WHEN** any module imports `from a2kit.packages.dispatch.substrate import Substrate`
- **THEN** an `ImportError` (or attribute access raise) fires with hint pointing to `Surface`

### Requirement: `SurfaceRegistry` is the single source of mounted surfaces

A module-level `SURFACE_REGISTRY` SHALL be the canonical registry of Surface instances, keyed by `surface.name`. `register_surface(s)` SHALL reject duplicate names. `build_parent_app` SHALL walk the registry instead of hardcoded `_has_api_registrations` / `_has_mcp_registrations` branches; for each surface with non-empty registrations on the active runtime, it SHALL call `surface.bind(runtime, descriptors)` and mount the result at `/{surface.name}`.

#### Scenario: Third surface auto-mounts without serve-side edits

- **GIVEN** a test-only `TestSurface(DecoratorSurface[TestReg])` registered via `SURFACE_REGISTRY.register_surface(TestSurface())` and a tool exposed on `"test"`
- **WHEN** `build_parent_app(runtime)` runs
- **THEN** the resulting parent app has the TestSurface mounted at `/test`
- **AND** no code under `packages/serve.py` was modified

#### Scenario: Duplicate surface name rejected

- **GIVEN** an attempt to register two surfaces with `name = "api"`
- **WHEN** `SURFACE_REGISTRY.register_surface(...)` is called the second time
- **THEN** it raises with a duplicate-name error

### Requirement: `expose` is an open set validated against the registry

`ToolDescriptor.expose` SHALL be `tuple[str, ...]`. Validation SHALL query `SURFACE_REGISTRY.names()` at descriptor-build time; unknown names SHALL raise with the list of registered surfaces. `Literal["mcp", "api"]` typing SHALL be removed from public API.

#### Scenario: Unknown expose name rejected at build

- **GIVEN** `@app.read(expose=("mcp", "graphql"))` and no `graphql` surface registered
- **WHEN** `App.build()` runs
- **THEN** a build-time error names `"graphql"` and lists the registered surfaces
