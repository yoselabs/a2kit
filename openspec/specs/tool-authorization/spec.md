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

The `authorize=` kwarg accepted by `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` / `@app.api.<method>` / `@app.mcp.<feature>` SHALL be enforced uniformly across all dispatch surfaces by `AuthorizeGateStage` (HTTP path additionally bridged by `_apply_authorize_gate` in `packages/http/build.py`). The gate SHALL resolve the callable's parameters through `Container.call_scope` so authors can annotate `principal: Principal` plus any container-known type. A falsy return SHALL raise `AuthorizationDenied(reason, callable_name)`; HTTP maps it to 403 with body `{"error": "authorization_denied", "reason": ..., "callable": ...}`; MCP renders the same shape through `McpErrorRenderStage` into the `ToolError` JSON payload.

#### Scenario: Same authorize= callable denies on both surfaces uniformly

- **GIVEN** `@a2kit.read(authorize=lambda *, principal: "admin" in principal.scopes) async def admin_op(...): ...` exposed on both surfaces
- **WHEN** invoked via HTTP and via MCP with the same non-admin Principal
- **THEN** HTTP returns 403 with `{"error": "authorization_denied", ...}`
- **AND** MCP raises `ToolError` carrying the same structured fields
- **AND** the tool body is never invoked in either case

### Requirement: `auth.testing.make_principal` is the supported Principal factory for tests

`a2kit.packages.auth.testing.make_principal(*, subject, scopes=(), claims=None, issued_by="test")` SHALL construct a `Principal` for unit-test use, mirroring the default Principal shape. Tests that need to publish a Principal without spinning up middleware use the named bridge writer API directly (`a2kit.packages.dispatch._principal_bridge.set_request_principal` / `reset_request_principal`), or override the DI provider on an `App` (`app.container().provide(Principal, lambda: fake)`). The previous `authenticated_as` contextmanager was removed in `consolidate-principal-bridge` as a redundant wrapper.

#### Scenario: make_principal returns the documented default shape

- **WHEN** `make_principal(subject="u1")` is called
- **THEN** the result is a `Principal` with `subject="u1"`, `scopes=frozenset()`, `claims={}`, `issued_by="test"`, `raw_token=None`

#### Scenario: Tool body resolves Principal via the named bridge writer API

- **GIVEN** `async def me(*, principal: Principal) -> str: return principal.subject`
- **AND** `token = set_request_principal(make_principal(subject="u1"))`
- **WHEN** the tool body is dispatched (per-call DI scope reads the bridge)
- **THEN** the result is `"u1"`
- **AND** `reset_request_principal(token)` restores the prior state

### Requirement: 401 vs 403 stay distinct on HTTP

Authentication failures (no credentials / bad credentials) SHALL return HTTP 401 with `{"error": "authentication_failed", "reason": <short>}`. Authorization failures (authenticated but denied by `authorize=`) SHALL return HTTP 403 with `{"error": "authorization_denied", "reason": ..., "callable": ...}`. Authentication middlewares own 401s; the gate owns 403s.

#### Scenario: Missing credentials yields 401 from middleware, not 403 from gate

- **GIVEN** an App with `APIKeyAuth(...)` and a tool with `authorize=...`
- **WHEN** a request arrives without the API key header
- **THEN** the response is 401 from the auth middleware
- **AND** the `authorize=` gate is never invoked
