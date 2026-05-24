## ADDED Requirements

### Requirement: `build_parent_app` SHALL mount surfaces via registry walk

`packages/serve.py:build_parent_app` SHALL walk `SURFACE_REGISTRY` instead of hardcoded `_has_api_registrations` / `_has_mcp_registrations` branches. For each surface with non-empty registrations on the active runtime, it SHALL call `surface.bind(runtime, descriptors)` and mount the result at `/{surface.name}`. The hardcoded `_has_*` helpers SHALL be deleted.

#### Scenario: Third surface auto-mounts without serve-side edits

- **GIVEN** a test-only `TestSurface(DecoratorSurface[TestReg])` registered via `SURFACE_REGISTRY.register_surface(TestSurface())` and a tool exposed on `"test"`
- **WHEN** `build_parent_app(runtime)` runs
- **THEN** the resulting parent app has the TestSurface mounted at `/test`
- **AND** no code under `packages/serve.py` was modified

### Requirement: `expose` SHALL be an open set validated against the registry

`ToolDescriptor.expose` SHALL be `tuple[str, ...]`. Validation SHALL query `SURFACE_REGISTRY.names()` at descriptor-build time; unknown names SHALL raise with the list of registered surfaces. `Literal["mcp", "api"]` typing SHALL be removed from public API.

#### Scenario: Unknown expose name rejected at build

- **GIVEN** `@app.read(expose=("mcp", "graphql"))` and no `graphql` surface registered
- **WHEN** `App.build()` runs
- **THEN** a build-time error names `"graphql"` and lists the registered surfaces

### Requirement: `Substrate` Literal import SHALL raise with migration hint

`a2kit.packages.dispatch.substrate.Substrate` SHALL no longer exist. Any attempt to import or attribute-access `Substrate` from that module SHALL raise with a hint pointing to `Surface` / `SURFACE_REGISTRY`.

#### Scenario: Substrate import raises with migration hint

- **WHEN** any module evaluates `from a2kit.packages.dispatch.substrate import Substrate`
- **THEN** an `ImportError` (or attribute-access raise) fires with a message naming `Surface` as the replacement
