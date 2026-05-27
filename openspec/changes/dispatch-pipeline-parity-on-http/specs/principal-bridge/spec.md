## MODIFIED Requirements

### Requirement: Principal is published via `request_scope.publish(p)`

Substrate authentication boundary code (`packages/auth/api_key`, `packages/mcp/principal_middleware`, **and `packages/http/_principal_middleware`**) SHALL publish the request `Principal` via `a2kit.packages.context.request_scope.publish(p)` and SHALL reset via `request_scope.reset(token)` in a `finally` block.

The HTTP path's Principal-publish seam SHALL live in a dedicated `packages/http/_principal_middleware.py` module that runs after the auth-middleware stack. It SHALL read whatever the auth path produced (FastAPI Security guard return value, request state, or middleware-attached attribute) and publish through the single `request_scope.publish` call. The publish/reset pair SHALL bracket the downstream chain in a `try`/`finally`.

The previous behaviour of scraping the Principal from per-call kwargs inside `_apply_authorize_gate` SHALL be removed; `_apply_authorize_gate` itself SHALL be deleted.

#### Scenario: HTTP middleware publishes and resets

- **GIVEN** an HTTP request whose auth path resolves a `Principal`
- **WHEN** the new `_principal_middleware` runs
- **THEN** `request_scope.publish(p)` is called before the downstream chain
- **AND** `request_scope.reset(token)` is called in a `finally` block
- **AND** after the request completes, `request_scope.try_get(Principal)` returns absent for subsequent unrelated requests

#### Scenario: MCP middleware publishes and resets (unchanged)

- **GIVEN** a substrate middleware extracts a `Principal` from the request
- **WHEN** the middleware calls `request_scope.publish(p)` and then invokes the downstream chain
- **THEN** `request_scope.get(Principal)` inside the downstream resolves to `p`
- **AND** after `request_scope.reset(token)` runs in the middleware's `finally` block, the lookup falls back to absent for subsequent unrelated requests

#### Scenario: `_apply_authorize_gate` is absent

- **WHEN** `grep -rn "_apply_authorize_gate\b" src/` runs
- **THEN** the output is empty
