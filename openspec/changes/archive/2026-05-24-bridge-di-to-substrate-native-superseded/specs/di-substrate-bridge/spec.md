## ADDED Requirements

### Requirement: `Container.expose_as_fastapi_depends(T)` produces a FastAPI-compatible resolver

`Container` SHALL expose `expose_as_fastapi_depends(type_: type) -> Callable[..., Any]`. The returned callable SHALL be a zero-arg function usable as a FastAPI `Depends(...)` dependency. When invoked inside a request, it SHALL read the active `_a2kit_scope` contextvar and return `scope.get(type_)`. When invoked outside any active `call_scope`, it SHALL raise `RuntimeError("a2kit Depends resolver called outside call_scope")`. Generated callables SHALL be cached per type on the container.

#### Scenario: FastAPI Security guard resolves a2kit DI

- **GIVEN** a FastAPI guard `def guard(*, principal: Principal, db: Database) -> Principal: ...` registered via `Security(...)`
- **AND** the `Database` type is provided by the a2kit container
- **WHEN** an HTTP request reaches a route protected by the guard
- **THEN** `principal` and `db` are both resolved from the active call scope
- **AND** the same `Database` instance is visible to the route handler

#### Scenario: Resolver outside scope raises

- **WHEN** the generated `Depends` callable is invoked with no active `_a2kit_scope`
- **THEN** `RuntimeError("a2kit Depends resolver called outside call_scope")` is raised

### Requirement: Substrate-dep is the fourth signature class

`split_signature` SHALL classify parameters into four buckets: substrate-reserved, container-resolved (lazy), substrate-dep (`Annotated[T, fastapi.params.Depends|Security]`), and wire. The bucket assignment SHALL be driven by `Surface.substrate_dep_markers`; substrates with an empty marker set SHALL produce no substrate-dep params. When substrate-dep params appear on an MCP-target wrapper, `SubstrateSignatureError` SHALL be raised at build time with hint `"FastAPI Depends/Security cannot appear on MCP-exposed tools; remove the marker or scope this tool with expose=('api',)"`.

#### Scenario: FastAPI Depends passes through to FastAPI

- **GIVEN** `@app.api.get("/sync") async def sync(*, principal: Annotated[Principal, Security(guard)], db: Database) -> SyncStatus: ...`
- **WHEN** the wrapper is built
- **THEN** `principal` is classified as substrate-dep (FastAPI resolves it via `guard`)
- **AND** `db` is classified as container-resolved (a2kit resolves it via the bridge)

#### Scenario: FastAPI Depends on MCP-exposed tool is rejected at build time

- **GIVEN** `@app.read async def fetch(*, who: Annotated[Principal, Depends(guard)], id: str) -> Memory: ...` with default `expose=("mcp","api")`
- **WHEN** `App.build()` runs
- **THEN** `SubstrateSignatureError` is raised with the documented hint
