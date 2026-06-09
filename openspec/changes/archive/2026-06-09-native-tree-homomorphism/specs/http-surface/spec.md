## MODIFIED Requirements

### Requirement: Projection tools become POST routes at `/api/{tool_name}`

For every projection tool with `"api" in expose`, the HTTP surface SHALL register a route `POST /api/{tool_name}` regardless of verb. Read/list/write verbs all map to POST. Rationale: the projection surface mirrors MCP's `tools/call` RPC shape over HTTP — one wire shape per tool, request body carries wire params as JSON, response body is the JSON-encoded return value. RESTful verb-mapping (`read`→GET) is intentionally NOT used because it would split each tool's contract across two HTTP methods, complicating idempotency semantics for clients that consume both `/api` and MCP.

`{tool_name}` SHALL be the tool's **canonical name** as resolved per `tool-descriptors` (`canonical_name_override` → `slug_leaf` for router verbs → bare `leaf` for app-level verbs). Router verbs SHALL be mounted via `FastAPI.include_router` (the homomorphism, ADR 0028 decision 3): each router becomes an `APIRouter` whose routes are included on the root app, carrying the slug as a grouping tag (`include_router(prefix=…, tags=[slug])` and/or `add_api_route(tags=[slug])`). The rendered route path SHALL be the flat canonical name (`/api/entity_update`), NOT a nested path (`/api/entity/update`) — the path segment is the canonical name so the wire identifier is byte-for-byte identical across MCP, HTTP, the CLI, and the audit log. The slug `tags` cluster the flat paths in the OpenAPI/Swagger document so flat names group without an extra drill-in. App-level verbs SHALL mount on the root app under their bare leaf (`/api/health`), with no slug prefix.

#### Scenario: Read-verb projection is also POST

- **GIVEN** `@a2kit.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** an HTTP client posts `{"id": "x"}` to `/api/fetch` with `Content-Type: application/json`
- **THEN** the response is `200 OK` with the JSON-encoded `Memory`
- **AND** `db: Database` was resolved by the a2kit Container
- **AND** `GET /api/fetch` returns `405 Method Not Allowed`

#### Scenario: Router verb mounts at the flat canonical path with a slug tag

- **GIVEN** `class Entity(a2kit.Router): slug = "entity"` with `@a2kit.read async def update(*, id: str) -> Memory: ...`
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** a route `POST /api/entity_update` exists (the flat canonical name), and `POST /api/update` does NOT
- **AND** the route is included via `include_router` and carries `tags=["entity"]` so the OpenAPI document groups it under the slug

#### Scenario: App-level verb stays bare at the root

- **GIVEN** an app-level verb `@a2kit.read async def health() -> Health: ...` with no owning router
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** the route is `POST /api/health` (bare leaf, no slug prefix), mounted directly on the root app

#### Scenario: Explicitly-pinned name is verbatim and unchanged

- **GIVEN** a verb under `slug="jira"` authored `@a2kit.read(canonical_name_override="jira_search")`
- **WHEN** the FastAPI app is assembled
- **THEN** the route is `POST /api/jira_search` exactly — the slug is not re-applied (never `/api/jira_jira_search`)
- **AND** the path is byte-for-byte identical to the pre-migration explicit-name route
