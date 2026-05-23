## ADDED Requirements

### Requirement: HTTP build installs the DI bridge

`build_http_app` SHALL invoke `Container.expose_as_fastapi_depends(T)` for every container-known type referenced by any descriptor's wire or substrate-dep chain, registering the result in `fastapi_app.dependency_overrides`. The wrapper body SHALL open the per-call scope before any FastAPI dependency callable runs, so substrate-dep callables observe the active `_a2kit_scope` contextvar.

#### Scenario: dependency_overrides populated for container-known types

- **GIVEN** an app with `Database` registered in the container and `@app.api.get("/x") async def x(*, principal: Annotated[Principal, Security(guard)], db: Database): ...`
- **WHEN** `build_http_app(runtime)` returns
- **THEN** `fastapi_app.dependency_overrides` contains entries for `Database` and `Principal`
- **AND** both resolve through the active `_a2kit_scope` contextvar
