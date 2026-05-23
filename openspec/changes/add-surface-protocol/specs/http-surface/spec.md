## ADDED Requirements

### Requirement: `ApiSurface` satisfies the `Surface` Protocol

`ApiSurface` SHALL subclass `DecoratorSurface[ApiRoute]` and SHALL set `name = "api"`, `reserved_types = frozenset({Request, Response, BackgroundTasks, WebSocket})`, `substrate_dep_markers = frozenset({fastapi.params.Depends, fastapi.params.Security})`. The body of `build_http_app` SHALL move into `ApiSurface.bind`; the existing function SHALL become a thin shim calling `ApiSurface().bind(...)` (or be removed entirely, raising with a migration hint to `ApiSurface().bind` if removed). `packages/http/__init__.py` SHALL register `ApiSurface()` with `SURFACE_REGISTRY` at lazy load.

#### Scenario: ApiSurface registered at lazy load

- **WHEN** `import a2kit.packages.http` first runs in a fresh interpreter
- **THEN** `SURFACE_REGISTRY.get("api")` returns the `ApiSurface()` singleton
