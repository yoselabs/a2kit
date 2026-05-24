## ADDED Requirements

### Requirement: `App.auth(spec)` accumulates AuthSpec instances

`App.auth(spec: AuthSpec) -> None` SHALL append `spec` to an internal `AppAuthRegistry`. Multiple calls SHALL accumulate in registration order. `AppRuntime.auth_registry` SHALL expose the materialised registry to substrate builders (`build_http_app`, `build_mcp_server`).

#### Scenario: Multiple auth specs accumulate in registration order

- **GIVEN** `app.auth(APIKeyAuth(...))` followed by `app.auth(JwtAuth(...))`
- **WHEN** the App is built
- **THEN** `runtime.auth_registry` yields `[APIKeyAuth(...), JwtAuth(...)]` in that order

### Requirement: Bundled wrappers expose three concrete AuthSpec types

`a2kit.packages.auth` SHALL export three concrete `AuthSpec` types as the bundled author-facing surface: `GoogleAuth` (OAuth wrapper around FastMCP's Google provider for `/mcp`), `APIKeyAuth` (API-key middleware for `/api`), `JwtAuth` (JWKS-backed JWT middleware for `/api`). Authors SHALL NOT need to import from `fastmcp.server.auth.providers.*`, `python-jose`, or transport substrate packages to configure auth.

#### Scenario: Author configures Google OAuth without touching FastMCP namespace

- **WHEN** an author writes `from a2kit.packages.auth import GoogleAuth; app.auth(GoogleAuth(...))`
- **THEN** no `fastmcp.server.auth.providers.*` import appears in author code

### Requirement: Cold-start invariant — `import a2kit` SHALL NOT pull auth deps

`import a2kit` SHALL NOT load `a2kit.packages.auth` or any of its submodules. `import a2kit.packages.auth` SHALL NOT pull `fastmcp.server.auth.providers.*`, `python-jose`, `cryptography`, or `httpx`. Heavy imports MUST live inside the submodule for each provider and load only when the matching `AuthSpec` is constructed or its middleware is built.

#### Scenario: Bare a2kit import leaves auth absent from sys.modules

- **WHEN** a process executes `import a2kit` in a fresh interpreter
- **THEN** `a2kit.packages.auth` is absent from `sys.modules`
- **AND** `fastmcp.server.auth.providers.google` is absent
- **AND** `jose` is absent

#### Scenario: Auth-package import leaves provider deps absent

- **WHEN** a process executes `import a2kit.packages.auth` in a fresh interpreter
- **THEN** `fastmcp.server.auth.providers.google` is absent from `sys.modules`
- **AND** `jose` / `python-jose` / `httpx` are absent

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
- **AND** the response body does NOT include the registered key set or any constant-time-leak hint

### Requirement: JwtAuth verifies signature, audience, issuer, and expiry

`JwtAuth(jwks_url, audience, issuer, algorithms=("RS256",))` SHALL ship an ASGI middleware that reads a bearer token from `Authorization: Bearer <jwt>`, fetches JWKS from `jwks_url` with TTL caching (default 10 min), verifies signature against the matching key, validates `aud` matches `audience` and `iss` matches `issuer` and `exp` is in the future, then synthesises a `Principal` from `sub`/`scope`/`scp`/full claims. Verification failures → 401 with the same envelope as `APIKeyAuth`.

#### Scenario: Valid JWT resolves to Principal carrying claims

- **GIVEN** `JwtAuth(jwks_url=..., audience="a", issuer="i")` and a JWT signed by the JWKS-listed key with `aud=a`, `iss=i`, `sub=u1`, `scope="reader writer"`
- **WHEN** a request arrives with `Authorization: Bearer <jwt>`
- **THEN** `principal.subject == "u1"`, `principal.scopes == frozenset({"reader", "writer"})`, `principal.claims` contains the full decoded payload

#### Scenario: Expired token returns 401

- **GIVEN** a JWT whose `exp` is in the past
- **WHEN** validated by `JwtAuth`
- **THEN** the response is 401 with `{"error": "authentication_failed", "reason": "token expired"}`

### Requirement: GoogleAuth.to_fastmcp_provider() yields a configured GoogleProvider

`GoogleAuth` SHALL expose `to_fastmcp_provider() -> fastmcp.server.auth.providers.google.GoogleProvider` that constructs the provider with the configured client_id, client_secret, base_url, and any additional fields the FastMCP provider requires. The import of `fastmcp.server.auth.providers.google` SHALL happen inside this method, not at module load.

#### Scenario: Provider is constructed lazily

- **GIVEN** `GoogleAuth(client_id=..., client_secret=..., base_url=...)` constructed in a fresh interpreter
- **WHEN** `to_fastmcp_provider()` has NOT been called
- **THEN** `fastmcp.server.auth.providers.google` is absent from `sys.modules`
- **WHEN** `to_fastmcp_provider()` is called
- **THEN** it returns a `GoogleProvider` instance configured with the supplied fields

### Requirement: Build-time wiring is opt-in per registry contents

`build_http_app` SHALL mount `APIKeyAuth` middleware only when `runtime.auth_registry` contains an `APIKeyAuth` spec. Same for `JwtAuth`. `build_mcp_server` SHALL pass `auth=` to `FastMCP(...)` only when the registry contains an OAuth-targeting spec (e.g. `GoogleAuth`). An App with zero `App.auth(...)` calls SHALL produce substrate apps with no auth middleware or provider attached.

#### Scenario: No-auth App produces middleware-free FastAPI sub-app

- **GIVEN** an App with no `App.auth(...)` calls
- **WHEN** `build_http_app(runtime)` runs
- **THEN** the resulting FastAPI app has no API-key or JWT middleware in its middleware stack
