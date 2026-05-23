## MODIFIED Requirements

### Requirement: `build_parent_app` mounts only substrates with registrations

`build_parent_app(app)` SHALL auto-determine which substrate sub-apps to mount based on the runtime's **post-selector-filter** registrations:

- The FastAPI sub-app SHALL be mounted under `/api` if and only if, after applying any `--select` selectors, at least one projection tool with `"api" in expose` OR at least one author-written `@app.api.*` route remains.
- The FastMCP sub-app SHALL be mounted under `/mcp` if and only if, after applying selectors, at least one projection tool with `"mcp" in expose` OR at least one `@app.mcp.*` registration remains.

If neither substrate has registrations after filtering, `build_parent_app` SHALL raise `ConfigError` with a message naming "no surfaces have registrations to expose after selector filter."

The auto-mount rule from `add-multi-surface` is extended here only in its observation point: the count is taken after selector application, not before. The mounting logic itself is unchanged.

#### Scenario: --select 'surface=mcp' skips the FastAPI mount

- **GIVEN** an `App` with `@app.read async def fetch(*, id)` (default `expose=("mcp","api")`) and `@app.api.get("/health")` (REST-only)
- **WHEN** the app is started with `serve --transport=http --select 'surface=mcp'`
- **THEN** the projection tool's `expose` is filtered to `("mcp",)` and the `.api.get` route is filtered out
- **AND** the FastAPI sub-app has zero registrations remaining
- **AND** the multiplex skips the `/api` mount — `/api/*` requests return 404 from the Starlette parent (the port is bound; only the prefix is absent)

#### Scenario: --select 'surface=api' skips the FastMCP mount

- **GIVEN** the same `App` above
- **WHEN** the app is started with `serve --transport=http --select 'surface=api'`
- **THEN** the projection tool's `expose` is filtered to `("api",)` and the `.mcp.*` registrations (none in this example) are filtered out
- **AND** the multiplex skips the `/mcp` mount

#### Scenario: All-filtered raises ConfigError

- **GIVEN** an `App` with only `@app.read` projection tools (default expose both)
- **WHEN** the app is started with `serve --select 'verb=write'` (excludes all read tools, no write tools exist)
- **THEN** `ConfigError` is raised
- **AND** the message contains "no surfaces have registrations to expose after selector filter"
