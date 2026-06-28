# tool-authorization Specification

## Purpose

Per-tool `authorize=` gate enforced uniformly across all dispatch
surfaces, plus the standard test seam for unit-testing
`authorize=` callables without spinning up middleware.

The dispatch wiring itself (`AuthorizeGateStage`,
`AuthorizationDenied`, HTTP 403 mapping, MCP error envelope) landed
via `propagate-principal-and-authorize`. This capability documents
the cross-cutting expectations identity providers and tool authors
rely on, plus the `auth.testing` helpers.

Materialized from `add-auth` (archived 2026-05-25).
## Requirements
### Requirement: `authorize=` enforcement is uniform across surfaces

The `authorize=` kwarg accepted by `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` / `@app.api.<method>` / `@app.mcp.<feature>` SHALL be enforced uniformly across all dispatch surfaces. For projection verbs and `@app.api.<method>` the gate runs as `AuthorizeGateStage` inside the dispatch pipeline (HTTP path additionally bridged by `_apply_authorize_gate` in `packages/http/build.py`). For `@app.mcp.<feature>` — which bypasses the dispatch pipeline by construction — the same gate SHALL be applied at registration time to the substrate-wrapped callable, reusing the one `AuthorizeGateStage` evaluation logic, so the escape hatch is not an authorization gap. The gate SHALL resolve the callable's parameters through `Container.call_scope` so authors can annotate `principal: Principal` plus any container-known type. A falsy return SHALL raise `AuthorizationDenied(reason, callable_name)` on every surface; HTTP maps it to 403 with body `{"error": "authorization_denied", "reason": ..., "callable": ...}`; MCP renders the same shape through `McpErrorRenderStage` into the `ToolError` JSON payload.

#### Scenario: Same authorize= callable denies on both surfaces uniformly

- **GIVEN** `@a2kit.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(...): ...` exposed on both surfaces
- **WHEN** invoked via HTTP and via MCP with the same non-admin Principal
- **THEN** HTTP returns 403 with `{"error": "authorization_denied", ...}`
- **AND** MCP raises `ToolError` carrying the same structured fields
- **AND** the tool body is never invoked in either case

#### Scenario: `@app.mcp.*` enforces authorize= at registration

- **GIVEN** `@app.mcp.tool(name="admin_dash", authorize=lambda *, principal: "admin" in principal.scopes)`
- **WHEN** the tool is invoked via MCP with a non-admin Principal
- **THEN** it raises `AuthorizationDenied` rendered through `McpErrorRenderStage` into the `ToolError` JSON payload
- **AND** the tool body is never invoked

#### Scenario: An authorized Principal passes the `@app.mcp.*` gate

- **GIVEN** the same `@app.mcp.tool(authorize=...)` registration
- **WHEN** the tool is invoked via MCP with an admin Principal
- **THEN** the gate passes and the tool body runs normally

### Requirement: `auth.testing.make_principal` is the supported Principal factory for tests

`a2kit.packages.auth.testing.make_principal(*, subject, scopes=(), claims=None, issued_by="test")` SHALL construct a `Principal` for unit-test use, mirroring the default Principal shape. Tests that need to publish a Principal without spinning up middleware use the shared request-scope bridge directly (`a2kit.packages.context.request_scope.publish(p)` / `reset(token)`), or override the DI provider on an `App` (`app.container().provide(Principal, lambda: fake)`).

#### Scenario: make_principal returns the documented default shape

- **WHEN** `make_principal(subject="u1")` is called
- **THEN** the result is a `Principal` with `subject="u1"`, `scopes=frozenset()`, `claims={}`, `issued_by="test"`, `raw_token=None`

#### Scenario: Tool body resolves Principal via the shared request-scope bridge

- **GIVEN** `async def me(*, principal: Principal) -> str: return principal.subject`
- **AND** `token = request_scope.publish(make_principal(subject="u1"))`
- **WHEN** the tool body is dispatched (per-call DI scope reads the bridge)
- **THEN** the result is `"u1"`
- **AND** `request_scope.reset(token)` restores the prior state

### Requirement: 401 vs 403 stay distinct on HTTP

Authentication failures (no credentials / bad credentials) SHALL return HTTP 401 with `{"error": "authentication_failed", "reason": <short>}`. Authorization failures (authenticated but denied by `authorize=`) SHALL return HTTP 403 with `{"error": "authorization_denied", "reason": ..., "callable": ...}`. Authentication middlewares own 401s; the gate owns 403s.

#### Scenario: Missing credentials yields 401 from middleware, not 403 from gate

- **GIVEN** an App with `APIKeyAuth(...)` and a tool with `authorize=...`
- **WHEN** a request arrives without the API key header
- **THEN** the response is 401 from the auth middleware
- **AND** the `authorize=` gate is never invoked

