## ADDED Requirements

### Requirement: Container bridges to FastAPI `Depends` via `expose_as_fastapi_depends`

`Container` SHALL provide `expose_as_fastapi_depends(type_: type) -> Callable[..., Any]` returning a FastAPI-compatible resolver that reads the active `_a2kit_scope` contextvar. Generated callables SHALL be cached on the container so identical-type calls return the same callable object.

#### Scenario: Container-known type resolvable via FastAPI Depends

- **GIVEN** a `Database` type registered with the a2kit container
- **AND** a FastAPI guard `def guard(*, db: Database) -> str: return db.name`
- **WHEN** an HTTP request reaches a route protected by `Security(guard)`
- **THEN** `guard` resolves `db` from the active a2kit call scope
- **AND** the same instance is visible to the route handler
