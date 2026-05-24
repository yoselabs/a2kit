## ADDED Requirements

### Requirement: `authorize=` kwarg has runtime providers via `App.auth(...)`

The `authorize=` kwarg surface reserved by `add-multi-surface` SHALL have first-class identity providers via `App.auth(...)` — `GoogleAuth` for MCP OAuth, `APIKeyAuth` + `JwtAuth` for HTTP. The kwarg's enforcement (already landed in `propagate-principal-and-authorize`) SHALL receive a `Principal` from these providers via the shared `_a2kit_request_principal` contextvar, without per-substrate author code.

#### Scenario: Single authorize= callable consumes Principal from either surface's auth provider

- **GIVEN** an App with `APIKeyAuth(...)` registered AND `GoogleAuth(...)` registered AND a tool `@a2kit.read(authorize=admin_only)`
- **WHEN** the same tool is invoked via HTTP (admin API key) and via MCP (admin OAuth scope)
- **THEN** `admin_only(principal=...)` runs in both paths against a Principal that carries the admin scope, without surface-specific author code
