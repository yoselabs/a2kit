# Pattern: remote-MCP access for web-only AI clients

## Motivation

ADR 0010 keeps a2kit's CLI auth-agnostic and parks an explicit
gap: AI agents that can only speak remote MCP — ChatGPT custom
connectors, Claude web, Gemini web, hosted Claude Desktop variants
— cannot run an a2kit CLI on the user's machine. For tools where
that matters, the answer is **expose the relevant operation as an
MCP verb**, not retrofit auth into the CLI.

This pattern shows what "expose responsibly" means in concrete
terms: how a verb running on a remote server knows *which*
authenticated user it's serving, how server-side state is scoped
to that user, and which operation shapes belong in a remote MCP
at all. Auth layer is **Google per ADR 0011**; no alternatives in
scope here (the self-hosted OIDC sub-recipe in ADR 0011 is a
documented deviation, not part of this pattern). Deployment shape
is **one OAuth app per server per ADR 0012**; no gateway.

The working reference implementation lives at
`examples/mcp_google_auth/`. The example is exercised by CI so
a2kit-side drift against this pattern fails at the framework
boundary, not in downstream consumers.

## The pattern

### Per-user UserSession via per-call DI

A small per-call DI factory reads the authenticated email from
FastMCP's active access token (Google JWT claims) and produces a
`UserSession` value object with `email: str` and
`workspace_dir: Path`. Verbs that need user context declare
`user: UserSession` in their signature and receive an instance via
DI under the per-call scope (ADR 0009).

```python
@dataclass(frozen=True)
class UserSession:
    email: str
    workspace_dir: Path

def build_user_session() -> UserSession:
    from fastmcp.server.dependencies import get_access_token
    token = get_access_token()
    if token is None:
        raise RuntimeError("no access token — auth layer not installed")
    email = token.claims["email"]
    return UserSession(
        email=email,
        workspace_dir=_workspace_dir_for(email, WORKSPACE_ROOT),
    )

app.provide(UserSession, build_user_session, per_call=True)
```

CLI mode (ADR 0010 — no auth) uses a parallel factory that reads
`$USER` and constructs `<user>@local`. The two factories produce
structurally identical `UserSession` objects without the CLI
pretending to be authenticated; the composition root in
`build_cli_app()` registers the CLI factory, and `build_mcp_app()`
registers the MCP factory. Same verb signatures, different wiring
at the root — the override pattern is ADR 0006.

**Why not promote `UserSession` to a2kit?** It's example code, not
framework code. Two consumers can converge on the same shape
without it becoming an a2kit type. When a third consumer files
friction asking for a shared type, that becomes an ADR. Until
then, copying ~20 lines is cheaper than a primitive.

### Workspace directories named by SHA-256 of the email

Per-user workspace directory name is the first 16 hex characters
of `sha256(email.lower().strip())`. The raw email never appears in
the directory name; a `_email` file written on first creation
preserves it for forensics, and `UserSession.email` carries the
raw email for any verb that needs to log human-readable
identifiers.

**Why hash, not raw email?** Characters legal in emails (`+`, `.`)
cause confusion in some filesystem contexts. More importantly,
`ls` on the workspace root would leak the test-user list to
anyone with read access. The hash is stateless, deterministic,
filesystem-safe, and one-way — reversal isn't needed because the
email lives in `UserSession.email`.

### Liftability rubric — which operations belong in remote MCP

Authors decide per verb. The framework does not enforce these
categories.

**Lift.** Read or search over server-owned state. Content
generation. Structured queries that return data, not side
effects. The bulk of useful verbs land here. Examples:
`search_knowledge`, `get_user_settings`, `summarize_doc`,
`list_recent_notes`.

**Lift with care.** Mutations on server-owned state. Time-consuming
operations. Anything that costs money. Pattern: small, idempotent,
loud failures. Examples: `note_write`, `enqueue_job`,
`update_settings`. The example's `note_write` is in this category.

**Don't lift.** Operations on the user's local filesystem outside
the server's workspace. OS interop. Anything that assumes the
user's local machine (open a file in Cursor, run a shell command
on the user's box). Web-only AI clients cannot reach these
*by design*; the right answer is "run the server locally if you
need it," not "let a remote server reach back to the user's
machine."

**Never lift.** Anything bypassing the auth layer. Anything that
escapes the per-user workspace. Anything that mutates other users'
data. These don't get a CLI version either — they shouldn't exist.

The example demonstrates *lift* (`whoami`, `note_read`) and *lift
with care* (`note_write`). It does not include any *don't lift*
verbs; if you need one in your server, write it CLI-only and
document the gap to remote callers.

## Deviation paths

- **Non-Google auth (self-hosted OIDC).** Use the sub-recipe in
  ADR 0011: generic `OAuthProxy` + `JWTVerifier(jwks_uri=...)`
  pointed at Authelia ≥ 4.40 / Authentik / Keycloak / Pocket-ID.
  The IdP is the OAuth server; Google (if used) is a federated
  upstream identity inside it, not the OAuth server. **Never stack
  Authelia in front of Google.** That anti-pattern is the
  Authelia-MCP failure mode documented in ADR 0012.
- **Multi-tenant beyond per-user.** Out of scope for this pattern.
  Tenant-level RBAC, shared workspaces, organization billing —
  none of those have an answer here. Build them in your server
  and file friction if the missing primitives matter.
- **Operations that can't lift.** Use the rubric. CLI-only is a
  legitimate answer; web-only AI clients live without them. ADR
  0010 chose this trade deliberately.

## References

- ADR 0010 — auth is MCP-mode only; CLI never authenticates.
- ADR 0011 — prescribed FastMCP Google + persistent-storage
  recipe.
- ADR 0012 — one OAuth app per server, no gateway.
- ADR 0006 — composition-root re-registration (how CLI and MCP
  modes register different `UserSession` factories).
- ADR 0009 — per-call DI scoping (the lifecycle that `UserSession`
  lives in).
- `mcp-context-passthrough` capability — how `fastmcp.Context`
  reaches verb bodies under the MCP transport.
- `examples/mcp_google_auth/` — the canonical worked
  implementation, exercised by CI.
