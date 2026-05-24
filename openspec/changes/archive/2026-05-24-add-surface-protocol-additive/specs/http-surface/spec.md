## ADDED Requirements

### Requirement: `ApiSurface` satisfies the `Surface` Protocol

`ApiSurface` SHALL subclass `DecoratorSurface[ApiRoute]` and SHALL set `name = "api"`, `reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket})`, `substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`. The body of `build_http_app` SHALL move into `ApiSurface.bind`; the existing function SHALL become a thin shim calling `ApiSurface().bind(...)`. `packages/http/__init__.py` SHALL register `ApiSurface()` with `SURFACE_REGISTRY` at lazy load.

#### Scenario: ApiSurface registered at lazy load

- **WHEN** `import a2kit.packages.http` first runs in a fresh interpreter
- **THEN** `SURFACE_REGISTRY.get("api")` returns an `ApiSurface()` instance

#### Scenario: build_http_app remains observably equivalent

- **GIVEN** a runtime with one `@app.read` tool and one `@app.api.get("/x")` route
- **WHEN** `build_http_app(runtime)` runs (the thin shim)
- **THEN** the resulting FastAPI app has both routes mounted, identical to pre-migration behaviour
