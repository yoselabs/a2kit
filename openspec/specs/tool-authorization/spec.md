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

### Requirement: `auth.testing.authenticated_as(principal)` binds the request contextvar

`a2kit.packages.auth.testing.authenticated_as(principal: Principal)` SHALL be a context manager that sets `_a2kit_request_principal` to `principal` on enter and resets on exit (success or exception). This SHALL be the supported way to unit-test `authorize=` callables and tool bodies without spinning up middleware. `make_principal(*, subject, scopes=())` SHALL be a factory mirroring the default Principal shape.

#### Scenario: authenticated_as resets contextvar on exception

- **GIVEN** `_a2kit_request_principal.get() is None` outside the block
- **WHEN** `with authenticated_as(p): raise RuntimeError("boom")` runs
- **THEN** `RuntimeError` propagates AND `_a2kit_request_principal.get() is None` after the block

#### Scenario: Tool body resolves Principal under authenticated_as

- **GIVEN** `async def me(*, principal: Principal) -> str: return principal.subject`
- **WHEN** invoked under `authenticated_as(make_principal(subject="u1"))`
- **THEN** the result is `"u1"`

### Requirement: 401 vs 403 stay distinct on HTTP

Authentication failures (no credentials / bad credentials) SHALL return HTTP 401 with `{"error": "authentication_failed", "reason": <short>}`. Authorization failures (authenticated but denied by `authorize=`) SHALL return HTTP 403 with `{"error": "authorization_denied", "reason": ..., "callable": ...}`. Authentication middlewares own 401s; the gate owns 403s.

#### Scenario: Missing credentials yields 401 from middleware, not 403 from gate

- **GIVEN** an App with `APIKeyAuth(...)` and a tool with `authorize=...`
- **WHEN** a request arrives without the API key header
- **THEN** the response is 401 from the auth middleware
- **AND** the `authorize=` gate is never invoked
