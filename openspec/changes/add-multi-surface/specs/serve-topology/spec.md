## MODIFIED Requirements

### Requirement: `serve --transport=http` runs a multiplexed server

When `serve` is invoked with `--transport=http`, the framework SHALL run a single process listening on a single port, serving every substrate that has registrations from an a2kit-owned parent ASGI application. Each substrate SHALL be a sub-application mounted under a distinct path prefix: the MCP substrate under `/mcp`, the HTTP substrate under `/api`. The parent application SHALL be run under an ASGI server (uvicorn). The author SHALL write no transport, mount, or server code to obtain this.

The substrates that get mounted SHALL be determined by the registrations on the `App` (see `surface-auto-mount`), not by explicit `--mcp`/`--rest` selection flags.

#### Scenario: One process serves both surfaces on one port

- **GIVEN** an `a2kit.App` with at least one projection tool exposed on both substrates (default `expose=("mcp","api")`)
- **WHEN** the app is started with `serve --transport=http --host=127.0.0.1 --port=8000`
- **THEN** a single process listens on `127.0.0.1:8000`
- **AND** the MCP streamable-HTTP endpoint is reachable under the `/mcp` path
- **AND** the HTTP substrate is reachable under the `/api` path

#### Scenario: MCP is served as a mounted sub-application

- **WHEN** the multiplexed server is built
- **THEN** the MCP surface is the Starlette application returned by `build_mcp_server(app).http_app(...)`, mounted on the parent application
- **AND** the parent application, not the FastMCP server, owns the uvicorn run

## REMOVED Requirements

### Requirement: Surface selection via `--mcp-only` and `--rest-only`

**Reason**: Replaced by registration-driven auto-mount (`surface-auto-mount` capability) and runtime selector override (`--select 'surface=...'`, defined in the `add-tool-select` change). The CLI no longer needs explicit selection flags because registrations declare intent and the selector handles deploy-time overrides without a flag explosion.

**Migration**:
- Remove any `--mcp-only` / `--rest-only` flags from `serve` invocations.
- For "MCP only" deployments of a mixed app: `serve --transport=http --select 'surface=mcp'` (note: requires the `add-tool-select` change).
- For deployments wanting only one substrate at the code level: omit registrations for the unwanted substrate — auto-mount will skip it.

### Requirement: stdio `serve` is a single-protocol MCP surface

**Reason**: The stdio path's surface selection is no longer governed by `--mcp-only` / `--rest-only` flags. The transport itself constrains what's possible: stdio is single-protocol MCP, full stop. The constraint stays the same; only the rejection-of-misuse mechanism changes.

**Migration**: Remove any `--mcp-only` flag from stdio invocations — it has no effect post-migration. Attempting to combine `--select 'surface=api'` with `--transport=stdio` SHALL be rejected with a usage error explaining stdio cannot carry HTTP.

