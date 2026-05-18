# mcp-google-auth — lintable reference

This example is the canonical worked implementation of the
**remote-MCP-access pattern** documented at
`docs/patterns/remote-mcp-access.md`. It implements the auth recipe
prescribed by ADR 0011 (Google + persistent storage + bearer escape
hatch) and the topology decision from ADR 0012 (one OAuth app per
server, no gateway). Its purpose is to be exercised by CI so any
a2kit-side drift against the recipe fails at the framework boundary,
not in downstream consumers.

It is intentionally tiny: three verbs (`whoami`, `note_write`,
`note_read`), one `UserSession` per-call DI provider, two
composition roots (CLI and MCP). All transport-clean per
ADR 0010 — auth lives only in the MCP composition root.

## Running

### Bearer-only mode (used by CI smoke test)

The simplest mode. No Google project, no interactive OAuth. Maps
static bearer tokens to fixture emails via the `StaticTokenVerifier`
escape hatch from ADR 0011.

```bash
export STATIC_TOKENS_JSON='{"T1":{"client_id":"smoke","scopes":["email"],"claims":{"email":"alice@example.com"}},"T2":{"client_id":"smoke","scopes":["email"],"claims":{"email":"bob@example.com"}}}'
export WORKSPACE_ROOT=/tmp/mcp-google-auth-workspaces

# Run the server (Streamable HTTP on :8000)
python -m examples.mcp_google_auth.server_main
```

Invoke `whoami` with `Authorization: Bearer T1` and you'll see
`alice@example.com`. Use `T2` and you'll see `bob@example.com` with
a distinct workspace.

### Full Google mode (the production recipe)

Set up a GCP project per ADR 0011's deployment notes:

1. Create an OAuth client in GCP, "Web application", redirect URI =
   `<PUBLIC_BASE_URL>/oauth/callback`.
2. Add up to 100 test users on the consent screen in "Testing" mode.
3. Generate a Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. (Single key, no salt needed — `FernetEncryptionWrapper` accepts a pre-built `Fernet` instance directly.)
4. Generate a JWT signing key: `openssl rand -hex 32`.

Then:

```bash
export GOOGLE_CLIENT_ID=...
export GOOGLE_CLIENT_SECRET=...
export JWT_SIGNING_KEY=...        # openssl rand -hex 32
export FERNET_KEY=...              # cryptography.fernet.Fernet key
export PUBLIC_BASE_URL=https://your-host
export WORKSPACE_ROOT=/var/lib/mcp-google-auth/workspaces
export TOKEN_CACHE_PATH=/var/lib/mcp-google-auth/oauth-cache

python -m examples.mcp_google_auth.server_main
```

Pitfalls (all documented in ADR 0011 in detail):

- **In-memory storage breaks daily reauth.** Always wire `client_storage`
  via `FernetEncryptionWrapper(DiskStore(...))`.
- **Missing `jwt_signing_key` breaks across restarts** even with
  persistent storage — tokens become unverifiable.
- **Google "Testing" mode expires refresh tokens every 7 days.**
  Policy, not bug. Plan for verification or accept weekly reauth.
- **Never put Authelia (or any IdP) in front of Google as the OAuth
  server.** Use Google directly per ADR 0012. Self-hosters use the
  generic OIDC sub-recipe (see ADR 0011) with their IdP as the
  OAuth server and Google as a federated upstream inside it.

## CLI mode

CLI mode has no auth (ADR 0010). The composition root in
`build_cli_app()` registers a fallback `UserSession` factory that
reads `$USER` and constructs `<user>@local` as the identity. Same
verb signatures, same shape — just no network identity.

```bash
python -m examples.mcp_google_auth.server whoami
```

CLI mode is for local development and for verbs that intentionally
do not lift to remote MCP. See the liftability rubric in
`docs/patterns/remote-mcp-access.md`.
