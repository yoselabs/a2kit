## ADDED Requirements

### Requirement: Future `Surface` implementations register via `PluginManifest`

Once `plugin-manifest` lands, every new `Surface`-Protocol implementation SHALL register via a `MANIFEST = PluginManifest(...)` constant in its package and SHALL be discovered through `load_surface(...)` at app boot. The imperative `SURFACE_REGISTRY.register_surface(...)` call path remains available for transitional purposes but SHALL NOT be the documented entry point for new surfaces.

The two existing surfaces (`mcp_surface`, `api_surface`) MAY remain on the imperative path until a separate migration change ports them — see BACKLOG entries "Registry-driven `expose=` validation" and "`A2K-SURFACE-REGISTRY` lint rule" for the consolidated follow-up.

#### Scenario: New surface ships a MANIFEST

- **GIVEN** a new package `packages/<surface>/` adding a `Surface`-Protocol implementation
- **WHEN** the package's `__init__.py` is imported at boot
- **THEN** the surface is discovered via its `MANIFEST` constant (not via an imperative `register_surface(...)` call in user code)

#### Scenario: Lint rule binds against the manifest shape

- **WHEN** a `Surface`-Protocol class lands without an accompanying `MANIFEST` in the same package
- **THEN** the pytest-archon rule `A2K-SURFACE-REGISTRY` fails and names the missing manifest
