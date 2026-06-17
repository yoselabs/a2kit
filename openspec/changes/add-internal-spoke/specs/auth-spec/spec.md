## MODIFIED Requirements

### Requirement: Auth specs declare their target surface and build their own middleware

`AuthSpec` subclasses SHALL declare the surface they apply to via the `target`
ClassVar. `target` SHALL NOT be restricted to `Literal["api", "mcp"]`: it SHALL
accept any registered surface name (e.g. `"internal"`), so a spoke or other
consumer-defined surface can be an auth target.

Each `AuthSpec` SHALL expose `build_middleware()` returning the ASGI middleware
factory that authenticates for that spec and publishes the resolved `Principal`
via `request_scope`. Substrate builders SHALL mount auth **generically** by
iterating `registry.for_target(surface.name)` and calling `spec.build_middleware()`
— they SHALL NOT branch on concrete spec types (no `isinstance` chain) and SHALL
NOT hardcode a surface name. An App with no `App.auth(...)` calls SHALL still
produce a middleware-free sub-app.

#### Scenario: A custom auth strategy mounts without an isinstance gate

- **WHEN** an App registers an `AuthSpec` subclass whose `target` is `"internal"`
- **THEN** the internal surface's builder mounts that spec's `build_middleware()`
  via `for_target("internal")`, with no per-class `isinstance` branch

#### Scenario: Existing API-key auth is unchanged

- **WHEN** an App registers `APIKeyAuth` (target `"api"`)
- **THEN** the HTTP surface mounts it via `build_middleware()` with the same
  request behavior (401 on missing/invalid key, `Principal` published on success)
  as before the generalization

## ADDED Requirements

### Requirement: TokenAuth validates dynamic leases per request

a2kit SHALL provide a `TokenAuth(AuthSpec)` strategy that authenticates a
presented token by calling a consumer-supplied `resolve(token) -> Principal | None`
**on every request** (not materialised once at build, unlike `APIKeyAuth`). On a
non-`None` result it SHALL publish that `Principal` for the call; on `None` it
SHALL reject with 401. The `Principal`'s scopes (least privilege, from the
caller's grant) SHALL be evaluated by `authorize=` gates uniformly with any other
surface's principal.

Because resolution is per request, revoking a token from the live set SHALL take
effect on the next call with no fixed expiry required. a2kit SHALL NOT own the
lease table or its lifecycle: `TokenAuth` reads only the `resolve` closure it is
handed, keeping the table (and any secret) outside a2kit.

#### Scenario: A live lease authenticates a long-running caller

- **WHEN** `resolve` returns a `Principal` for a token, and a caller presents it
  repeatedly over a long span
- **THEN** every call authenticates with the lease's scopes, with no TTL-driven
  mid-span expiry

#### Scenario: Revocation is immediate

- **WHEN** the token is removed from the live set the runner exposes via `resolve`
- **THEN** the next call presenting it is rejected with 401
