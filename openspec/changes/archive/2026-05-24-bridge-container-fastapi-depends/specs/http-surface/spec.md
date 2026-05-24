## ADDED Requirements

### Requirement: HTTP build installs the DI bridge

`build_http_app` SHALL invoke `Container.expose_as_fastapi_depends(T)` for every container-known type referenced by any descriptor's wire or substrate-dep chain, registering the result in `fastapi_app.dependency_overrides`. The wrapper body SHALL open the per-call `_a2kit_scope` before any FastAPI dependency callable runs, so substrate-dep callables observe the active contextvar.

#### Scenario: dependency_overrides populated for container-known types

- **GIVEN** an app with `Database` registered in the container and an `@app.api.get` route whose handler uses `Annotated[Database, Depends(get_db_stub)]`
- **WHEN** `build_http_app(runtime)` returns
- **THEN** `fastapi_app.dependency_overrides` contains an entry whose key resolves to `Database`
- **AND** the registered resolver returns the container's scoped `Database` instance on every request
