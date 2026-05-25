## ADDED Requirements

### Requirement: register_surface() side-effects into a kernel-layer name registry

`SURFACE_REGISTRY.register_surface(s)` SHALL, as a side-effect, append `s.name` to a kernel-layer (L0/L1) name registry exposed via `registered_surface_names() -> tuple[str, ...]`. The name registry MUST be importable from the `authoring` core sub-unit (L2) without violating the layer DAG. Duplicate-name registration MUST NOT add the name twice.

#### Scenario: Registering a surface populates the name registry

- **GIVEN** a fresh interpreter with no surfaces imported
- **WHEN** `a2kit.packages.mcp` and `a2kit.packages.http` are imported
- **THEN** `registered_surface_names()` returns a tuple containing `"mcp"` and `"api"` (in registration order)

#### Scenario: Name registry is layer-clean from authoring

- **WHEN** the lint rule `A2K-LAYER` is run against `src/a2kit/_verbs.py` (or wherever the verbs live)
- **AND** that file imports `registered_surface_names` from the kernel name-registry module
- **THEN** the lint rule reports no violation

#### Scenario: Duplicate registration does not duplicate the name

- **GIVEN** a Surface registered once
- **WHEN** `SURFACE_REGISTRY.register_surface(...)` is called again with the same name (which raises per existing spec)
- **THEN** `registered_surface_names()` still contains the name exactly once
- **AND** the duplicate-name error from the existing spec is unchanged
