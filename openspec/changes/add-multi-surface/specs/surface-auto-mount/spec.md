## ADDED Requirements

### Requirement: `build_parent_app` mounts only substrates with registrations

`build_parent_app(app)` SHALL auto-determine which substrate sub-apps to mount based on the runtime's registrations:

- The FastAPI sub-app SHALL be mounted under `/api` if and only if at least one of the following is true: the runtime contains at least one projection tool with `"api" in expose`, OR at least one author-written `@app.api.*` route.
- The FastMCP sub-app SHALL be mounted under `/mcp` if and only if at least one of the following is true: the runtime contains at least one projection tool with `"mcp" in expose`, OR at least one `@app.mcp.*` registration.

If neither substrate has registrations, `build_parent_app` SHALL raise `ConfigError` with a message naming "no surfaces have registrations to expose."

`build_parent_app` SHALL NOT accept explicit `mcp` or `rest` boolean kwargs for surface selection (replaced by registration-driven auto-mount; deployment-time override is via the separate `--select 'surface=...'` mechanism).

#### Scenario: Only FastAPI mounts when only `.api` routes are registered

- **GIVEN** an `App` with `@app.api.get("/health")` and no projection or `@app.mcp.*` registrations
- **WHEN** `build_parent_app(app)` is called
- **THEN** the returned Starlette parent has a single `/api` mount
- **AND** `/mcp` is not mounted

#### Scenario: Both mount when projection has default expose

- **GIVEN** an `App` with `@app.read async def fetch(...)` (default `expose=("mcp", "api")`)
- **WHEN** `build_parent_app(app)` is called
- **THEN** the parent has both `/api` and `/mcp` mounts

#### Scenario: Empty registrations raise ConfigError

- **GIVEN** an `App` with zero tools, zero routes, zero MCP features
- **WHEN** `build_parent_app(app)` is called
- **THEN** `ConfigError` is raised
- **AND** the message contains "no surfaces have registrations to expose"
