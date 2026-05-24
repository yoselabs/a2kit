## ADDED Requirements

### Requirement: Surface identity SHALL flow through Surface objects, not strings

The framework SHALL NOT discriminate substrates by string literal. `split_signature` and `install_substrate_signature` SHALL take a `Surface` object and consume `surface.reserved_types` / `surface.substrate_dep_markers` directly. No new branch on a substrate name string SHALL appear in dispatch-layer code.

#### Scenario: Signature splitter consumes Surface attributes uniformly

- **GIVEN** `split_signature(fn, surface, container)` for any `surface in SURFACE_REGISTRY`
- **WHEN** it classifies parameters
- **THEN** reserved-type detection uses `surface.reserved_types` and substrate-dep detection uses `surface.substrate_dep_markers`
- **AND** no `if surface_name == "fastapi"` / `"fastmcp"` branch executes
