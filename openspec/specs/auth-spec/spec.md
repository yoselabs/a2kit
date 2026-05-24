# auth-spec Specification

## Purpose

Author-facing surface for configuring authentication on a2kit Apps.
`App.auth(spec)` accumulates :class:`AuthSpec` instances; substrate
builders (`build_http_app`, future `build_mcp_server` integration)
consume them through `runtime.auth_registry`.

Bundled surface today: `APIKeyAuth` for HTTP API keys. `JwtAuth` and
`GoogleAuth` are queued as follow-up changes; the spec only documents
what has actually landed so spec-drift gates stay green.

Materialized from `add-auth` (archived 2026-05-25).

## Requirements

### Requirement: `App.auth(spec)` accumulates AuthSpec instances

`App.auth(spec: AuthSpec) -> App` SHALL append `spec` to an internal `AppAuthRegistry`. Multiple calls SHALL accumulate in registration order. `AppRuntime.auth_registry` SHALL expose the materialised registry to substrate builders (`build_http_app` today; `build_mcp_server` once an MCP-targeting wrapper lands).

#### Scenario: Multiple auth specs accumulate in registration order

- **GIVEN** `app.auth(APIKeyAuth(...))` followed by a second `app.auth(APIKeyAuth(..., header="X-Alt-Key"))`
- **WHEN** the App is built
- **THEN** `runtime.auth_registry.all()` returns the two specs in that order

#### Scenario: No auth call leaves registry None

- **GIVEN** an App with no `App.auth(...)` calls
- **WHEN** `app.auth_registry` is accessed
- **THEN** it is `None` (no allocation, no `packages.auth` import triggered by accessor)

### Requirement: Cold-start invariant — `import a2kit` SHALL NOT pull auth deps

`import a2kit` SHALL NOT load `a2kit.packages.auth` or any of its submodules. `import a2kit.packages.auth` SHALL NOT pull `fastmcp.server.auth.providers.*`, `python-jose` / `jose`, `httpx`. Heavy imports MUST live inside their concrete-provider submodules and load only when the matching `AuthSpec` is constructed or its middleware is built.

#### Scenario: Bare a2kit import leaves auth absent from sys.modules

- **WHEN** a process executes `import a2kit` in a fresh interpreter
- **THEN** `a2kit.packages.auth` is absent from `sys.modules`

#### Scenario: Auth-package import leaves provider deps absent

- **WHEN** a process executes `import a2kit.packages.auth` in a fresh interpreter
- **THEN** `fastmcp.server.auth.providers.google` is absent from `sys.modules`
- **AND** `jose` / `python_jose` / `httpx` are absent

### Requirement: APIKeyAuth synthesises a Principal per request

`APIKeyAuth` SHALL ship an ASGI middleware that reads the configured header (default `X-API-Key`), looks up the key in the registered set, synthesises a `Principal(subject=key.subject, scopes=key.scopes, claims={}, issued_by="api-key", raw_token=None)`, and publishes it on `_a2kit_request_principal` for the request lifetime. `raw_token` SHALL be `None` — keys MUST NOT be echoed onto the propagated identity. Missing header → 401. Unknown key → 401. Both use the JSON envelope `{"error": "authentication_failed", "reason": <short>}`.

#### Scenario: Valid key resolves to Principal with declared scopes

- **GIVEN** `APIKeyAuth(keys=[ApiKey("k1", subject="alice", scopes={"reader"})])`
- **WHEN** a request arrives with `X-API-Key: k1`
- **THEN** the tool body sees `principal: Principal` with `subject == "alice"`, `scopes == frozenset({"reader"})`, `issued_by == "api-key"`, `raw_token is None`

#### Scenario: Missing key returns 401

- **GIVEN** `APIKeyAuth(keys=[...])` registered on an App
- **WHEN** a request arrives without the configured header
- **THEN** the response is 401 with body `{"error": "authentication_failed", "reason": "missing API key"}`

#### Scenario: Bad key returns 401 without leaking the registered set

- **GIVEN** `APIKeyAuth(keys=[ApiKey("k1", ...)])`
- **WHEN** a request arrives with `X-API-Key: WRONG`
- **THEN** the response is 401 with `{"error": "authentication_failed", "reason": "invalid API key"}`
- **AND** the response body does NOT include the registered key set

### Requirement: Build-time wiring is opt-in per registry contents

`build_http_app` SHALL mount `APIKeyAuth` middleware only when `runtime.auth_registry` contains an `APIKeyAuth` spec. An App with zero `App.auth(...)` calls SHALL produce a FastAPI sub-app with no auth middleware attached.

#### Scenario: No-auth App produces middleware-free FastAPI sub-app

- **GIVEN** an App with no `App.auth(...)` calls
- **WHEN** `build_http_app(runtime)` runs
- **THEN** the resulting FastAPI app has no API-key middleware in its middleware stack
