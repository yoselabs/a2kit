# Pattern: authenticating a networked a2kit MCP endpoint (Google)

## Motivation

An a2kit MCP server served over HTTP (`a2kit serve --transport http
--host 0.0.0.0`) exposes an **open port**: any caller that reaches it
can invoke every advertised tool. ADR 0010 keeps a2kit itself
auth-agnostic on the MCP surface — the framework does not own an OAuth
abstraction — so the answer is *not* an `a2kit.packages.auth` wrapper.
It is a FastMCP OAuth provider handed straight to `FastMCP(auth=...)`.

ADR 0011 prescribes **one blessed recipe** so every a2kit-based MCP
server starts from a path that works on day one and encodes the
pitfalls (in-memory token loss, missing `jwt_signing_key`,
DCR-incompatible clients, Google "Testing"-mode reauth) rather than
re-discovering them. This document is that recipe. a2web is its first
consumer.

> **Scope.** `a2kit.packages.auth` (`APIKeyAuth`, `TokenAuth`) covers
> the **HTTP/REST** surface and the internal spoke. It does **not**
> ship a `GoogleAuth` or `JwtAuth` symbol — MCP OAuth lives here, in
> host-server code, by design (ADR 0010).

## Where the provider plugs in

`build_mcp_server(app, **fastmcp_kwargs)` forwards every extra kwarg
straight to `FastMCP.__init__` — including `auth=`. The `serve`
multiplex threads the same kwargs through its `mcp_options` mapping.
So the wiring is one kwarg deep; the only question is *who calls the
serve entrypoint*.

- **Programmatic entrypoint (required for OAuth).** You construct the
  provider (an object, not a string) and pass it via `mcp_options`.
- **`a2kit serve` CLI.** Populates only `compact` / `tool_selection` /
  `code_mode` / `code_mode_allow_destructive`. There is no `--auth`
  flag — a `GoogleProvider` cannot be expressed on a command line — so
  an auth-bearing server ships a ~15-line `__main__` instead of the
  bare CLI.

```python
# yourserver/__main__.py   (container CMD: python -m yourserver)
import asyncio
from a2kit.packages.serve import serve_process
from fastmcp.server.auth.providers.google import GoogleProvider

def _provider():
    if not (settings.google_client_id and settings.google_client_secret):
        return None  # unset creds => server stays open (LAN/Tailscale only)
    return GoogleProvider(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        base_url=settings.public_base_url,        # see "The base_url sharp edge"
        jwt_signing_key=settings.jwt_signing_key, # REQUIRED — see pitfalls
        client_storage=_token_store(),            # REQUIRED — see pitfalls
        required_scopes=["openid", "email"],
    )

def main() -> None:
    app = build_app()
    provider = _provider()
    asyncio.run(serve_process(
        app,
        transport="http", host="0.0.0.0", port=8000, internal_uds=None,
        mcp_options={"auth": provider} if provider else None,
    ))

if __name__ == "__main__":
    main()
```

`mcp_options` is documented as the serve-knob channel, but because it
splats into `build_mcp_server(**mcp_options)` it accepts any FastMCP
kwarg. `auth=` is the supported passthrough for exactly this.

## How the authenticated identity reaches a verb

Nothing extra to wire. `build_mcp_server` always mounts
`PrincipalMiddleware`, which reads FastMCP's active `access_token`
(populated by the provider after a successful OAuth exchange) and
publishes a `Principal` onto the dispatch bridge for the call. A verb
that declares `principal: Principal` (or reads Google claims via
`fastmcp.server.dependencies.get_access_token()`) receives the caller
identity under the per-call DI scope. See
`docs/patterns/remote-mcp-access.md` for the per-user `UserSession`
shape built on top of this.

## The blessed recipe (Google + small beta)

Per ADR 0011, pin these choices; deviate only with a documented reason.

- **Provider:** `GoogleProvider` (offline access is the 2.13.2+
  default). FastMCP `>= 3.2, < 4`.
- **`jwt_signing_key` — REQUIRED.** Load from a stable env var
  (`openssl rand -hex 32`). Without it, tokens persisted across a
  restart cannot be re-validated and every restart forces a reauth.
  Store it outside the repo (1Password / vault / `.env`); rotation
  invalidates all live sessions (acceptable for a small beta).
- **Token storage — REQUIRED, persistent + encrypted.** A filesystem
  `key_value` `DiskStore` wrapped in `FernetEncryptionWrapper`. The
  in-memory default loses all tokens on restart (daily-reauth trap).

  ```python
  from key_value.aio.stores.disk import DiskStore            # needs the diskcache extra
  from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

  def _token_store():
      raw = DiskStore(directory=settings.oauth_cache_dir)    # ~/.local/share/<server>/oauth
      return FernetEncryptionWrapper(store=raw, fernet_key=settings.fernet_key)
  ```

- **Bearer escape hatch:** mount a `StaticTokenVerifier`
  (`fastmcp.server.auth.providers.jwt.StaticTokenVerifier`), env-gated,
  for DCR-incompatible clients (Cline, Continue) and as the fallback
  if Google "Testing"-mode 7-day reauth becomes unworkable.
- **Transport:** Streamable HTTP only. SSE is deprecated — do not
  enable it.
- **Beta gating:** GCP OAuth consent screen in "Testing" mode with
  explicit test users (100-user cap). The GCP project is the allowlist;
  keep no allowlist in code.
- **Deployment:** one GCP OAuth app per server, no gateway (ADR 0012).
  Do **not** stack Authelia (or any second OAuth server) in front of
  Google — that reproduces the documented Authelia-MCP failure mode.

## The base_url sharp edge

`GoogleProvider` **requires** `base_url`, and the OAuth redirect URI is
derived as `base_url + redirect_path`. That redirect URI must be
registered exactly in the GCP OAuth client. Therefore:

- `base_url` is the **public** URL clients reach (e.g.
  `https://mcp.example.com`), not `--host`. It cannot be derived from
  `0.0.0.0` or from the bind address — those are private and would
  produce a redirect Google rejects.
- Supply it explicitly (env / settings). When the server runs behind a
  reverse proxy or Tailscale MagicDNS name, `base_url` is that public
  name, and the proxy must forward it untouched.

## Self-hosted OIDC (deviation sub-recipe)

For a non-Google IdP (Authelia ≥ 4.40, Authentik, Keycloak,
Pocket-ID): use a generic `OAuthProxy` + `JWTVerifier(jwks_uri=...)`
(`fastmcp.server.auth.providers.jwt.JWTVerifier`) pointed at the IdP.
Same storage / signing-key / transport / bearer-fallback rules. The
IdP is the OAuth server MCP clients see; Google (if used at all) is a
federated upstream identity *inside* the IdP, never the OAuth server
in front of MCP.

## Interim: shipping open

If OAuth is not yet wired, ship **open** and say so loudly: bind
`--host 0.0.0.0` only behind Tailscale or a private LAN, and state in
the deployment README that the port must not be exposed publicly until
the provider lands. This is the never-silently-miss discipline applied
to the deploy contract — do not claim an auth guarantee the server
cannot keep. `APIKeyAuth`/`TokenAuth` can gate the **REST** surface
with a bearer token in the meantime, but they do not protect the MCP
OAuth flow.

## References

- ADR 0010 — auth is an MCP-mode concern only; a2kit is auth-agnostic
  on the MCP surface (no `GoogleAuth`/`JwtAuth` in `packages.auth`).
- ADR 0011 — this prescribed Google + persistent-storage recipe.
- ADR 0012 — one OAuth app per server, no gateway.
- `docs/patterns/remote-mcp-access.md` — per-user `UserSession` and the
  liftability rubric built on the `Principal` this recipe produces.
- `a2kit.packages.mcp.build_mcp_server` — `auth=` passthrough.
- `a2kit.packages.serve` — `mcp_options={"auth": ...}` passthrough.
- FastMCP Google provider: <https://gofastmcp.com/servers/auth/oauth-proxy>
- Google Testing-mode policy: <https://support.google.com/cloud/answer/15549945>
