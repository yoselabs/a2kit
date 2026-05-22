# serve-topology Specification

## Purpose
TBD - created by archiving change multiplex-serve-topology. Update Purpose after archive.
## Requirements
### Requirement: `serve --transport=http` runs a multiplexed server

When `serve` is invoked with `--transport=http`, the framework SHALL run a single process listening on a single port, serving every enabled surface from an a2kit-owned parent ASGI application. Each surface SHALL be a sub-application mounted under a distinct path prefix: the MCP surface under `/mcp`, the REST surface under `/api`. The parent application SHALL be run under an ASGI server (uvicorn). The author SHALL write no transport, mount, or server code to obtain this.

#### Scenario: One process serves both surfaces on one port

- **GIVEN** an `a2kit.App` with at least one registered tool
- **WHEN** the app is started with `serve --transport=http --host=127.0.0.1 --port=8000`
- **THEN** a single process listens on `127.0.0.1:8000`
- **AND** the MCP streamable-HTTP endpoint is reachable under the `/mcp` path
- **AND** the REST surface is reachable under the `/api` path

#### Scenario: MCP is served as a mounted sub-application

- **WHEN** the multiplexed server is built
- **THEN** the MCP surface is the Starlette application returned by `build_mcp_server(app).http_app(...)`, mounted on the parent application
- **AND** the parent application, not the FastMCP server, owns the uvicorn run

### Requirement: Surface selection via `--mcp-only` and `--rest-only`

The `serve` command SHALL accept two mutually exclusive flags, `--mcp-only` and `--rest-only`, both defaulting to off. With neither flag set, every surface applicable to the transport SHALL be served (opt-out, never opt-in). `--mcp-only` SHALL serve only the MCP surface; `--rest-only` SHALL serve only the REST surface. Passing both SHALL be rejected as a usage error.

#### Scenario: Default serves all surfaces

- **WHEN** the app is started with `serve --transport=http` and no surface flag
- **THEN** both the MCP surface and the REST surface are mounted

#### Scenario: `--mcp-only` serves MCP alone

- **WHEN** the app is started with `serve --transport=http --mcp-only`
- **THEN** the MCP surface is mounted
- **AND** no REST surface is mounted

#### Scenario: `--rest-only` serves REST alone

- **WHEN** the app is started with `serve --transport=http --rest-only`
- **THEN** the REST surface is mounted
- **AND** no MCP surface is built or mounted

#### Scenario: Both flags together is a usage error

- **WHEN** the app is started with `serve --transport=http --mcp-only --rest-only`
- **THEN** the command exits with a non-zero status and an error naming the conflict

### Requirement: stdio `serve` is a single-protocol MCP surface

The default `serve` transport (stdio) SHALL serve the MCP surface only, because a stdio pipe cannot multiplex more than one protocol. `--rest-only` combined with stdio SHALL be rejected as a usage error. `--mcp-only` combined with stdio SHALL be accepted as a redundant no-op.

#### Scenario: `--rest-only` is rejected on stdio

- **WHEN** the app is started with `serve` (stdio, default transport) and `--rest-only`
- **THEN** the command exits with a non-zero status and an error stating that REST cannot be served over stdio

#### Scenario: stdio still serves MCP

- **WHEN** the app is started with `serve` and no transport flag
- **THEN** the MCP surface is served over stdio exactly as before this change

### Requirement: The multiplex server dependency is imported lazily

The ASGI server (uvicorn) and the parent-application composition SHALL be imported only on the `serve --transport=http` path, never at `import a2kit`. `import a2kit` SHALL NOT import uvicorn.

#### Scenario: `import a2kit` does not import the ASGI server

- **WHEN** `import a2kit` runs in a fresh interpreter
- **THEN** `uvicorn` is absent from `sys.modules`

