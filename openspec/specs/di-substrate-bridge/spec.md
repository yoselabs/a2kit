# di-substrate-bridge Specification

## Purpose

The bridge lets substrates with their own dependency graphs (today: FastAPI's `Depends`/`Security`) resolve a2kit `Container`-known types via type annotation alone, without authors having to write `Depends(get_db_from_a2kit)` boilerplate or duplicate provider registrations. `Container.expose_as_fastapi_depends(T)` produces a FastAPI-compatible resolver; `build_http_app` wires it into `fastapi_app.dependency_overrides`. A per-request middleware publishes the a2kit child container on the `_a2kit_request_scope` contextvar so the resolver finds the active scope.

## Requirements
### Requirement: `Container.expose_as_fastapi_depends(T)` produces a FastAPI-compatible resolver

`Container` SHALL expose `expose_as_fastapi_depends(type_: type) -> Callable[..., Any]`. The returned callable SHALL be a zero-arg `async def` usable as a FastAPI `Depends(...)` dependency. When invoked inside a request, it SHALL read the active `_a2kit_request_scope` contextvar and return `scope.get(type_)`. When invoked outside any active call scope, it SHALL raise `RuntimeError("a2kit Depends resolver called outside call_scope")`. Generated callables SHALL be cached per type on the container so identity-stable callers (FastAPI's `Depends` key map) deduplicate correctly.

#### Scenario: FastAPI Security guard resolves a2kit DI

- **GIVEN** a FastAPI guard `def guard(db: Annotated[Database, Depends(Database)]) -> str: return db.name` registered via `Security(guard)`
- **AND** the `Database` type is provided by the a2kit container
- **WHEN** an HTTP request reaches a route protected by the guard
- **THEN** `db` is resolved from the active call scope
- **AND** the same `Database` instance is visible to the route handler that also injects `Database` via a2kit DI

#### Scenario: Resolver outside scope raises

- **WHEN** the generated `Depends` callable is invoked with no active `_a2kit_request_scope`
- **THEN** `RuntimeError("a2kit Depends resolver called outside call_scope")` is raised

#### Scenario: Resolver is cached per type

- **GIVEN** a container with `Database` registered
- **WHEN** `container.expose_as_fastapi_depends(Database)` is called twice
- **THEN** both calls return the same callable object (identity-equal)
