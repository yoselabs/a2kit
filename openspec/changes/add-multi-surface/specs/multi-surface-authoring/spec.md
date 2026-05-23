## ADDED Requirements

### Requirement: Three decorator families on `App`

`App` SHALL expose three decorator families that all use one shared signature-rewriting mechanism so a2kit DI is resolved by type annotation alone:

1. **Projection decorators**: `@app.read`, `@app.list`, `@app.write` SHALL register a tool on every substrate listed in the decorator's `expose` kwarg. Default `expose=("mcp", "api")`.
2. **REST-only decorators**: `app.api.<method>` SHALL register a route only on the FastAPI substrate, where `<method>` is one of `get`, `post`, `put`, `delete`, `patch`, `options`, `head`.
3. **MCP-only decorators**: `app.mcp.tool`, `app.mcp.prompt`, `app.mcp.resource` SHALL register the corresponding feature only on the FastMCP substrate.

All three families SHALL resolve a2kit DI from the author's function signature without requiring a `Depends(...)` marker, an `Annotated[T, Depends(...)]` marker, or any other framework-visible annotation.

#### Scenario: Projection registers on both substrates

- **GIVEN** an `App` with `@app.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** `build_parent_app(app)` is run with both substrates having registrations
- **THEN** the FastAPI mount exposes `POST /api/fetch`
- **AND** the FastMCP mount exposes a `tools/call` named `fetch`
- **AND** both handlers resolve `db: Database` from the same a2kit Container instance

#### Scenario: REST-only decorator with native FastAPI kwargs

- **GIVEN** `@app.api.get("/sync", response_model=SyncStatus, status_code=200) async def sync(*, mgr: SyncManager) -> SyncStatus: ...`
- **WHEN** the FastAPI sub-app is built
- **THEN** a route `GET /api/sync` is registered with the FastAPI native `response_model` and `status_code` semantics
- **AND** `mgr: SyncManager` is resolved by a2kit DI without any `Depends` marker

#### Scenario: MCP-only decorator registers a Prompt

- **GIVEN** `@app.mcp.prompt(name="summarize") async def s(*, topic: str, cfg: Config) -> list[Message]: ...`
- **WHEN** the FastMCP sub-app is built
- **THEN** the MCP `prompts/list` request returns a Prompt named `summarize`
- **AND** invoking it resolves `cfg: Config` via the a2kit Container

### Requirement: Substrate accessors `app.api.fastapi_app` and `app.mcp.fastmcp_server`

`app.api` SHALL expose a property `fastapi_app` returning the underlying `FastAPI` instance. `app.mcp` SHALL expose a property `fastmcp_server` returning the underlying `FastMCP` instance. Both properties SHALL be lazy — accessing them triggers the substrate import; not accessing them keeps the substrate out of `sys.modules`.

#### Scenario: Author adds substrate-native middleware via accessor

- **GIVEN** an `App` and a third-party Starlette middleware `GZipMiddleware`
- **WHEN** the author writes `app.api.fastapi_app.add_middleware(GZipMiddleware)`
- **THEN** the middleware is registered on the FastAPI sub-app and runs on every `/api/*` request

#### Scenario: Accessors are lazy

- **GIVEN** an `App` with no `@app.api.*` or `@app.mcp.*` registrations and no access to `app.api.fastapi_app` or `app.mcp.fastmcp_server`
- **WHEN** `import a2kit` and `app = App(...)` and tool registration completes
- **THEN** `fastapi` and `fastmcp` are absent from `sys.modules`
