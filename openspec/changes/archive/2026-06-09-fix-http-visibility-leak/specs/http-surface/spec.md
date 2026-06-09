## MODIFIED Requirements

### Requirement: Projection tools become POST routes at `/api/{tool_name}`

For every projection tool with `"api" in expose` **and resolved visibility `"all"`**, the HTTP surface SHALL register a route `POST /api/{tool_name}` regardless of verb. Read/list/write verbs all map to POST. Rationale: the projection surface mirrors MCP's `tools/call` RPC shape over HTTP — one wire shape per tool, request body carries wire params as JSON, response body is the JSON-encoded return value. RESTful verb-mapping (`read`→GET) is intentionally NOT used because it would split each tool's contract across two HTTP methods, complicating idempotency semantics for clients that consume both `/api` and MCP.

A projection tool whose resolved visibility is not `"all"` (i.e. `"cli"` or `"hidden"`) SHALL NOT be mounted on the HTTP surface — no `POST /api/{tool_name}` route and no DI `dependency_overrides` entry SHALL be registered for it. This mirrors the MCP surface, which already skips non-`"all"` tools. Visibility is resolved from the tool descriptor's metadata, defaulting to `"all"` when no metadata is present. CLI-only (`visibility="cli"`) and hidden (`visibility="hidden"`) verbs are therefore structurally unreachable over HTTP, not merely undocumented.

#### Scenario: Read-verb projection is also POST

- **GIVEN** `@a2kit.read async def fetch(*, id: str, db: Database) -> Memory: ...`
- **WHEN** an HTTP client posts `{"id": "x"}` to `/api/fetch` with `Content-Type: application/json`
- **THEN** the response is `200 OK` with the JSON-encoded `Memory`
- **AND** `db: Database` was resolved by the a2kit Container
- **AND** `GET /api/fetch` returns `405 Method Not Allowed`

#### Scenario: CLI-only verb is not mounted on HTTP

- **GIVEN** a router verb authored `@a2kit.write(visibility="cli") async def trust_vault(...): ...`
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** no `POST /api/trust_vault` route exists
- **AND** posting to `/api/trust_vault` returns `404 Not Found`
- **AND** no `dependency_overrides` entry was registered for that verb's Container-known parameters

#### Scenario: Hidden verb is not mounted on HTTP

- **GIVEN** a projection verb whose resolved visibility is `"hidden"`
- **WHEN** `build_http_app(runtime)` assembles the FastAPI app
- **THEN** the verb has no `/api` route, matching the MCP surface which also skips it

#### Scenario: HTTP and MCP apply the same visibility rule

- **GIVEN** a set of projection verbs with mixed visibility (`"all"`, `"cli"`, `"hidden"`)
- **WHEN** both `build_http_app(runtime)` and the MCP server registration run
- **THEN** exactly the `"all"`-visibility, `"api"`/`"mcp"`-exposed verbs are mounted on each respective surface
- **AND** no `"cli"`- or `"hidden"`-visibility verb is reachable on either network surface
