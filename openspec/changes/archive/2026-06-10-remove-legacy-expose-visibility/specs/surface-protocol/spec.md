## MODIFIED Requirements

### Requirement: `ToolDescriptor.expose` SHALL widen to `tuple[str, ...]`

`ToolDescriptor.expose` SHALL be `tuple[str, ...]` (not `tuple[Literal["mcp", "api"], ...]`). The `Literal["mcp", "api"]` typing SHALL be removed from the public descriptor surface. Build-time validation in `a2kit.runtime._validate_descriptor_expose` SHALL reject unknown surface names with a `TypeError` naming the composed surface set.

Surface-name validation runs at `runtime.build()` time against the composed `SURFACE_REGISTRY`, not at decoration: `_verbs` lives in the authoring layer (L2) and the registry lives in dispatch (L4); reading the registry from L2 would violate `A2K-LAYER`, so the check is deferred to the runtime layer where the registry is available. The legacy decoration-time `a2kit._verbs._validate_expose` helper is removed with the `expose=` kwarg; the mounted-surfaces tuple is now derived from the resolved `surfaces=` matrix.

#### Scenario: Unknown surface name rejected at build

- **GIVEN** `@a2kit.read(surfaces=("mcp", "graphql"))`
- **WHEN** `runtime.build()` runs against the composed default surface set
- **THEN** a `TypeError` names `"graphql"` and lists the composed surface set

#### Scenario: ToolDescriptor.expose type is open-set

- **WHEN** introspecting `ToolDescriptor.__annotations__["expose"]`
- **THEN** the type is `tuple[str, ...]`, not a `Literal` narrowing
