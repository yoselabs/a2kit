## ADDED Requirements

### Requirement: HTTP auth middleware is opt-in via `App.auth(...)`

`build_http_app` SHALL mount `APIKeyAuth` middleware iff `runtime.auth_registry` contains an `APIKeyAuth` spec. SHALL mount `JwtAuth` middleware iff the registry contains a `JwtAuth` spec. Middlewares SHALL run in registration order; the first to successfully authenticate wins (subsequent middlewares short-circuit on a populated `_a2kit_request_principal`). No default auth middleware SHALL be mounted; an App with zero `App.auth(...)` calls SHALL produce a FastAPI sub-app with no auth in its middleware stack.

#### Scenario: APIKeyAuth + JwtAuth co-mount; API-key header wins when both present

- **GIVEN** `app.auth(APIKeyAuth(...))` then `app.auth(JwtAuth(...))`
- **WHEN** a request arrives with both `X-API-Key: k1` and `Authorization: Bearer <jwt>`
- **THEN** `_a2kit_request_principal` is set by the API-key middleware
- **AND** the JWT middleware short-circuits without re-setting the principal

#### Scenario: Empty auth registry produces middleware-free FastAPI

- **GIVEN** an App with no `App.auth(...)` calls
- **WHEN** `build_http_app(runtime)` runs
- **THEN** inspecting `app.user_middleware` shows no `APIKeyAuth` or `JwtAuth` middleware classes mounted
