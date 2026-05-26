## MODIFIED Requirements

### Requirement: Surfaces are passive — no import-time registry mutation

Every class implementing the `Surface` Protocol SHALL be passive: importing its defining module MUST NOT mutate any module-level or global registry. Surfaces SHALL be composed explicitly at `AppRuntime` build time (see `serve-topology`). The previous pattern where `packages/<surface>/__init__.py` called `SURFACE_REGISTRY.register_surface(...)` at import time is forbidden by this requirement.

#### Scenario: Importing a surface front door does not register it

- **GIVEN** a fresh interpreter
- **WHEN** code does `import a2kit.packages.mcp` (and nothing else from a2kit)
- **THEN** no registry — module-level or runtime-scoped — contains `McpSurface`
- **AND** the front door's top-level statements consist only of `import`s, the `__getattr__` lazy resolver, and `__all__`

#### Scenario: Architecture test enforces passivity

- **WHEN** the architecture suite (per `arch-fitness-functions`, when landed) inspects every `Surface`-Protocol class
- **THEN** each defining module's top-level AST contains no call expression that touches `SURFACE_REGISTRY` or any equivalent global
