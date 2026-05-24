## ADDED Requirements

### Requirement: `A2K-SURFACE-REGISTRY` lint rule enforces registry registration

A new lint rule `A2K-SURFACE-REGISTRY` SHALL hard-fail any module under `src/a2kit/packages/` that defines a class satisfying the `Surface` Protocol without a corresponding `SURFACE_REGISTRY.register_surface(...)` call in its enclosing package's `__init__.py` lazy load.

#### Scenario: Surface subclass without registry registration is rejected

- **GIVEN** a new file `src/a2kit/packages/grpc/surface.py` defining `class GrpcSurface(DecoratorSurface[GrpcReg]): ...`
- **AND** `src/a2kit/packages/grpc/__init__.py` has no `SURFACE_REGISTRY.register_surface(GrpcSurface())` call
- **WHEN** `make lint` runs
- **THEN** `A2K-SURFACE-REGISTRY` raises naming the unregistered surface
