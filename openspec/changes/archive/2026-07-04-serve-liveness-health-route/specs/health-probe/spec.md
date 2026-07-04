## ADDED Requirements

### Requirement: Transport-native liveness route on HTTP serve

The multiplex parent SHALL expose a static liveness route at the root path `GET /health` returning HTTP 200 with body `{"status": "ok"}` whenever a2kit serves over HTTP (`serve --transport=http`), independent of which surfaces are mounted. The route SHALL be present for an MCP-only serve, an api-only serve, and a both-surfaces serve alike.

The liveness route SHALL be **dumb**: it SHALL NOT resolve DI, enter resources,
or aggregate surface health — a wedged DI graph SHALL still answer 200. Degraded
/ readiness aggregation remains the responsibility of the `_meta.health` tool;
the two SHALL stay separate.

The liveness route SHALL be reachable **without credentials** regardless of any
authentication strategy configured on a surface: it is a sibling of the surface
mounts on the parent application, which carries no authentication middleware.

The existing `/api/health` route on the FastAPI sub-app SHALL remain unchanged
(back-compatible for REST deployments).

#### Scenario: MCP-only serve exposes a liveness route

- **GIVEN** a runtime with only MCP registrations, served over HTTP
  (`--select surface=mcp`)
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 and the body is `{"status": "ok"}`

#### Scenario: api-only serve exposes the same root liveness route

- **GIVEN** a runtime with only `api`-surface registrations, served over HTTP
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 and the body is `{"status": "ok"}`

#### Scenario: both-surfaces serve exposes /health and keeps /api/health

- **GIVEN** a runtime with both MCP and `api` registrations, served over HTTP
- **WHEN** a client issues `GET /health` and `GET /api/health`
- **THEN** both return 200 with body `{"status": "ok"}`

#### Scenario: liveness answers with a wedged DI graph

- **GIVEN** an HTTP serve whose provider resolution would raise on any tool call
- **WHEN** a client issues `GET /health`
- **THEN** the response status is 200 — the route resolved no DI

#### Scenario: liveness is reachable without credentials

- **GIVEN** an HTTP serve with an authentication strategy configured on a
  surface (e.g. `APIKeyAuth` on `api`, or an MCP `auth=` provider)
- **WHEN** a client issues `GET /health` with no credentials
- **THEN** the response status is 200 — the parent-root route is not behind any
  surface's auth middleware

#### Scenario: no parent, no route

- **GIVEN** an App with no registrations on any surface
- **WHEN** `build_parent_app` is invoked
- **THEN** it raises `ValueError` (unchanged) and no `/health` route is served
