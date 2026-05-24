# Design — add-auth

## Audience model (locked by proposal)

Two audiences, two surfaces, one principal model:

- `/mcp` is OAuth-shaped. FastMCP's auth providers under
  `fastmcp.server.auth.providers.*` are spec-compliant for the
  evolving MCP auth flow; a2kit wraps them so authors don't import
  from that namespace directly.
- `/api` is API-key-shaped by default. Long-lived keys, simple
  rotation, no OAuth dance for programmatic use. JWT acceptance is a
  secondary opt-in path for HTTP clients that already hold a token
  from the MCP OAuth flow.

The `Principal` type — already landed by `propagate-principal-and-authorize`
— is the shared identity. Every auth path resolves to a `Principal`
and writes it into the per-call DI scope; `principal: Principal` is
the type authors annotate on `authorize=` callables and tool bodies.

## Module structure

```
src/a2kit/packages/auth/
  __init__.py            # PEP 562 facade — lazy imports, no auth deps at front door
  spec.py                # AuthSpec base + the three concrete configs (dataclasses)
  google.py              # GoogleAuth wrapper around fastmcp's Google provider
  api_key.py             # APIKeyAuth + middleware factory
  jwt.py                 # JwtAuth + middleware factory
  registry.py            # AppAuthRegistry — accumulator bound to App
```

Layer: L5 (transport-adjacent, on top of `mcp` and `http`). Same tier
as those substrate packages. `import a2kit.packages.auth` SHALL NOT
pull `fastmcp.server.auth.providers.*`, `python-jose`, or `httpx` —
each provider's heavy imports stay inside its own submodule, loaded
only when the matching `AuthSpec` is materialised by the App.

## Author surface

```python
import a2kit
from a2kit.packages.auth import GoogleAuth, APIKeyAuth, JwtAuth

app = a2kit.App("my-server")

# OAuth on /mcp via FastMCP's Google provider
app.auth(GoogleAuth(
    client_id="...",
    client_secret="...",
    base_url="https://...",
))

# API keys on /api (env / file / secrets-manager via callable)
app.auth(APIKeyAuth(
    keys=lambda: load_keys_from_secrets_manager(),
    header="X-API-Key",  # default
))

# Optional JWT on /api for SSO with the MCP OAuth issuer
app.auth(JwtAuth(
    jwks_url="https://.../.well-known/jwks.json",
    audience="my-audience",
    issuer="https://...",
))
```

`App.auth(spec)` appends to an internal `AppAuthRegistry`. Multiple
calls accumulate; order matters only for HTTP middleware (multiple
authentication strategies run in registration order, first match
wins).

## Authentication paths

### MCP path: OAuth via FastMCP provider

`GoogleAuth` is a thin dataclass; its `to_fastmcp_provider()` method
returns a configured `fastmcp.server.auth.providers.google.GoogleProvider`
instance. `build_mcp_server` reads the App's auth registry, looks for
an MCP-targeting spec, and passes the provider as `auth=` to
`FastMCP(...)`. The existing `PrincipalMiddleware` (landed by
`propagate-principal-and-authorize`) reads `Context.access_token`,
synthesises a `Principal`, and publishes it on
`_a2kit_request_principal`. The `DispatchHookStage` (and direct
substrate wrapper for substrate-native tools) seed the contextvar
value into `Container.call_scope` as a SCOPED provider keyed by
`type(value) = Principal`.

No new MCP-side wiring is required beyond the provider hand-off:
`PrincipalMiddleware` already extracts and propagates the identity.

### HTTP path: API-key middleware

`APIKeyAuth` ships an ASGI middleware factory:

```python
def build_api_key_middleware(spec: APIKeyAuth) -> Middleware:
    keys = _materialise_keys(spec.keys)  # resolves callable / env / file / etc.
    async def middleware(scope, receive, send):
        if scope["type"] != "http":
            return await app(scope, receive, send)
        header_value = _read_header(scope, spec.header)
        if header_value is None:
            return await _respond_401("missing API key")(scope, receive, send)
        principal = _principal_for_key(header_value, keys)
        if principal is None:
            return await _respond_401("invalid API key")(scope, receive, send)
        token = _a2kit_request_principal.set(principal)
        try:
            await app(scope, receive, send)
        finally:
            _a2kit_request_principal.reset(token)
    return middleware
```

`build_http_app` registers this middleware on the FastAPI sub-app
when the auth registry contains an `APIKeyAuth` spec. Missing keys
returns 401 with the documented JSON envelope; never falls through to
a 403 from the authorize-gate (which would mis-route the cause).

`Principal` shape from an API key:
- `subject = key.subject` (the operator-named identity for this key)
- `scopes = key.scopes` (frozenset)
- `claims = {}` (API keys carry no claims; structured fields live in the key registry)
- `issued_by = "api-key"` (constant)
- `raw_token = None` (never echo the key)

### HTTP path: JWT middleware

`JwtAuth` ships a second ASGI middleware factory consuming a JWKS-
backed verifier. Verifies signature, audience, issuer, expiry. On
success, synthesises a `Principal` from standard claims (`sub`,
`scope`/`scp`, the full claims dict). On failure, returns 401 with
the same JSON envelope as `APIKeyAuth`.

When both `APIKeyAuth` and `JwtAuth` are registered, the middlewares
run in registration order: first to recognise its header wins. A
request carrying neither falls through to the route handler with
`_a2kit_request_principal` unset; the `authorize=` gate then denies.

### Authorize-gate enforcement

`AuthorizeGateStage` already landed by
`propagate-principal-and-authorize`: it resolves the per-tool
`authorize=` callable through `call_scope` (typed-param DI) and
raises `AuthorizationDenied` on a falsy return. HTTP and MCP each map
the exception to their transport error.

This change adds NO new dispatch wiring. The `authorize=` kwarg has
been load-bearing since `propagate-principal-and-authorize` archived;
this change adds the upstream auth providers that supply identity.

## Error envelope

Authentication failures (no/bad credentials) → **401**, JSON body:

```json
{"error": "authentication_failed", "reason": "<short>"}
```

Authorization failures (authenticated but denied by `authorize=`) →
**403**, JSON body (existing shape from
`propagate-principal-and-authorize`):

```json
{"error": "authorization_denied", "reason": "...", "callable": "..."}
```

MCP authentication failures flow through FastMCP's own provider error
path (already spec-compliant); MCP authorization failures use the
existing structured envelope in `McpErrorRenderStage` (lands as
`{error: "authorization_denied", reason, callable}` in the
`ToolError` JSON payload).

## Test seam

A fixture `auth.testing` provides:

```python
def make_principal(*, subject: str, scopes: Iterable[str] = ()) -> Principal: ...

@contextlib.contextmanager
def authenticated_as(principal: Principal) -> Iterator[None]:
    """Bind a Principal on the request contextvar for the duration of the block."""
    token = _a2kit_request_principal.set(principal)
    try:
        yield
    finally:
        _a2kit_request_principal.reset(token)
```

This lets `authorize=` callables and tool bodies be tested without
spinning up middleware:

```python
async def test_admin_op_denies_non_admin():
    with authenticated_as(make_principal(subject="u1", scopes=())):
        with pytest.raises(AuthorizationDenied):
            await admin_op()
```

For FastAPI integration tests, `container.override(...)` and standard
`TestClient` headers (`{"X-API-Key": "..."}`) exercise the real path.

## Cold-start invariants

- `import a2kit` SHALL NOT load `a2kit.packages.auth` or any of its
  submodules.
- `import a2kit.packages.auth` SHALL NOT pull
  `fastmcp.server.auth.providers.*`, `python-jose`, `cryptography`,
  or `httpx`. Each provider's heavy imports live inside its own
  submodule, loaded only when the matching `AuthSpec` is constructed.
- `build_mcp_server` / `build_http_app` SHALL only consult the auth
  registry when registrations exist; an App with no `App.auth(...)`
  calls has zero auth-related imports anywhere in its boot path.

## Out of scope (deferred)

- Auth provider plug-in protocol for third-party identity providers.
  The three bundled providers (`GoogleAuth`, `APIKeyAuth`, `JwtAuth`)
  cover the common cases; opening this up cleanly needs a separate
  ADR.
- Role-based access control as a framework feature. `authorize=` +
  scope strings in `Principal.scopes` is the primary mechanism;
  richer RBAC stays in author code.
- mTLS, HMAC request signing, AWS-SigV4. Out of scope until a
  concrete user need surfaces.
- Multi-tenancy / per-App auth isolation in the same process. The
  registry is App-scoped; multi-App requires deliberate design.

## Dependencies (all landed)

- `Principal` type + `_a2kit_request_principal` contextvar:
  `propagate-principal-and-authorize`.
- `AuthorizeGateStage` + `AuthorizationDenied` + HTTP 403 / MCP
  envelope mapping: `propagate-principal-and-authorize`.
- FastAPI `Security(...)` substrate-dep passthrough:
  `add-substrate-dep-class`.
- `Container.expose_as_fastapi_depends` bridge:
  `bridge-container-fastapi-depends`.
- `Surface` Protocol + `SURFACE_REGISTRY`:
  `add-surface-protocol-additive` + `remove-substrate-literal`.
