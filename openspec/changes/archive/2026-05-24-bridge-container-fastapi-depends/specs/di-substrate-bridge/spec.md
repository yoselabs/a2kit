## ADDED Requirements

### Requirement: `Container.expose_as_fastapi_depends(T)` produces a FastAPI-compatible resolver

`Container` SHALL expose `expose_as_fastapi_depends(type_: type) -> Callable[..., Any]`. The returned callable SHALL be a zero-arg function usable as a FastAPI `Depends(...)` dependency. When invoked inside a request, it SHALL read the active `_a2kit_scope` contextvar and return `scope.get(type_)`. When invoked outside any active `call_scope`, it SHALL raise `RuntimeError("a2kit Depends resolver called outside call_scope")`. Generated callables SHALL be cached per type on the container.

#### Scenario: FastAPI Security guard resolves a2kit DI

- **GIVEN** a FastAPI guard `def guard(*, db: Database) -> str: return db.name` registered via `Security(...)`
- **AND** the `Database` type is provided by the a2kit container
- **WHEN** an HTTP request reaches a route protected by the guard
- **THEN** `db` is resolved from the active call scope
- **AND** the same `Database` instance is visible to the route handler

#### Scenario: Resolver outside scope raises

- **WHEN** the generated `Depends` callable is invoked with no active `_a2kit_scope`
- **THEN** `RuntimeError("a2kit Depends resolver called outside call_scope")` is raised

#### Scenario: Resolver is cached per type

- **GIVEN** a container with `Database` registered
- **WHEN** `container.expose_as_fastapi_depends(Database)` is called twice
- **THEN** both calls return the same callable object (identity-equal)
