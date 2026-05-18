---
id: "0011"
status: proposed
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [auth, mcp, recipe, docs, google]
deciders: [Denis Tomilin]
---

# ADR 0011: Prescribed FastMCP auth recipe — Google + persistent storage + bearer escape

## Status

Proposed, 2026-05-18. Pairs with ADR 0010 (auth is MCP-mode only).
Promote to `accepted` when the first downstream MCP server
(knowledge-mcp) ships using this recipe and proves it operationally
(no daily reauth, no token-loss-on-restart).

## Summary

In the context of remote a2kit-based MCP servers that need
authentication, facing a 2026 ecosystem where FastMCP 2.13+ ships
first-class providers but the configuration matrix is wide and
several pitfalls (in-memory token storage, missing `jwt_signing_key`,
Google "Testing" mode reauth, DCR-incompatible clients) cause
predictable failure, we decided to prescribe a single specific
recipe — FastMCP `GoogleProvider` + Fernet-wrapped filesystem
`py-key-value` store + stable `jwt_signing_key` from env +
`StaticTokenVerifier` bearer escape hatch + Streamable HTTP
transport + GCP "Testing" consent screen for beta gating — and
against documenting the full FastMCP option matrix in a2kit, to
achieve one reproducible blessed path that downstream MCP authors
can copy without re-discovering each pitfall, accepting that
self-hosters who want non-Google IdPs follow a different (also
prescribed) sub-recipe and that the recipe will need re-validation
as FastMCP releases roll forward.

## The problem

ADR 0010 leaves auth in the host server. Tool authors building
remote a2kit-based MCP servers (knowledge-mcp first, possibly
others) need to know *which* auth wiring to use. The FastMCP 2.13+
surface offers:

- 5+ first-class providers (Google, GitHub, Azure, AWS Cognito,
  Auth0) + generic OAuthProxy + bearer verifiers.
- 3+ token storage backends (in-memory, filesystem, Redis,
  Elasticsearch) with optional Fernet encryption.
- 2 transports (SSE, Streamable HTTP), one deprecated.
- A `jwt_signing_key` that, if omitted, makes tokens invalid after
  restart even with persistent storage.
- Beta-gating via GCP "Testing" mode (100-user cap, 7-day token
  expiry) or "Production" mode (verification required for
  sensitive scopes).

Authors who pick wrong combinations hit predictable failures:
daily reauth (in-memory storage), post-restart token invalidation
(missing `jwt_signing_key`), DCR-incompatible clients (no static
bearer fallback), or transport-layer reconnect storms (SSE).

Past consumer pain (Authelia-in-front-of-Google) compounds this:
the temptation to fix auth at the gateway layer leads to stacking
two OAuth servers, which collides with DCR direction, id_token
lifetime defaults, and PRM handling. The simplest correct path
needs to be named so it gets followed.

## What we considered (and why this one)

### Option 1: Document the full FastMCP matrix

Why it lost:

- **Decision burden moves to every downstream author.** Each new
  MCP server re-evaluates providers, storage, transport, signing
  key handling. Most pick wrong the first time.
- **Doesn't capture our learned-the-hard-way pitfalls.** The
  Authelia trap, the 7-day Testing-mode expiry, the
  `jwt_signing_key` requirement — these are not visible in
  FastMCP's reference docs at the level a glance gives.
- **No reproducibility across our consumer projects.** Each
  a2kit-based MCP server invents its own wiring; cross-cutting
  fixes don't propagate.

### Option 2: Prescribe one recipe (chosen)

Name the blessed path explicitly, ship it as a copy-pasteable
example, document the known pitfalls inline. Self-hoster
deviations are a named sub-recipe.

Why it wins:

- **One reproducible path.** Every a2kit-based MCP server starts
  from the same wiring; fixes propagate by version-bumping the
  recipe.
- **Encodes the pitfalls.** The recipe includes the
  `jwt_signing_key`, the Fernet wrapper, the `StaticTokenVerifier`
  fallback, the "Testing" mode warning — exactly the things that
  bit us before.
- **Matches AGENTS.md "one way to do things."** Authors don't
  pick; they copy. Deviation is a deliberate act with a documented
  alternative.

### Option 3: Ship the recipe as a2kit code (a Python module)

Why it lost:

- **Violates ADR 0010.** a2kit core is auth-agnostic. Shipping
  `a2kit.auth.google_recipe()` is exactly the abstraction ADR
  0010 rejects.
- **Couples a2kit's release cadence to FastMCP's.** Every FastMCP
  auth change forces an a2kit release.
- **The recipe is ~30 lines of host-server code.** Not enough
  surface to justify a module; enough to justify a docs page.

## The decision

The blessed recipe is a documentation artifact at
`docs/patterns/mcp-auth.md` (to be written when the first consumer
adopts it). It prescribes:

### Google + small-beta (the primary recipe)

- **FastMCP**: `>= 3.2` (a2kit pins `fastmcp >= 3.2, < 4`; the auth
  surface stabilised across the 2.13 → 3.x bump and the recipe
  applies identically). The recipe was originally validated against
  the 2.13 line where these providers landed; FastMCP 3.x preserves
  the API.
- **Provider**: `GoogleProvider` (offline access is default in
  2.13.2+).
- **Token storage**: filesystem `py-key-value` store wrapped in
  `FernetEncryptionWrapper`. Path: `~/.local/share/<server-name>/oauth/cache.db`
  by default; override via env.
- **JWT signing key**: `jwt_signing_key` loaded from a stable env
  var. Required — without it, persisted tokens cannot be
  re-validated after server restart.
- **Bearer escape hatch**: `StaticTokenVerifier` mounted alongside,
  controlled by env. Used for DCR-incompatible clients (Cline,
  Continue) and as the fallback if Google "Testing" mode 7-day
  reauth becomes unworkable.
- **Transport**: Streamable HTTP only. SSE is deprecated; do not
  enable it.
- **Beta gating**: GCP OAuth consent screen in "Testing" mode with
  explicit test users (100-user cap). No allowlist in code; the
  GCP project is the source of truth.
- **Documented pitfalls inline**: 7-day Testing-mode token expiry
  (Google policy, not a bug); how to graduate to "In production"
  (sensitive-scope verification, weeks); the "do not stack
  Authelia in front of Google" rule.

### Self-hosted OIDC (the sub-recipe)

For users who want a non-Google IdP (Authelia ≥ 4.40, Authentik,
Keycloak, Pocket-ID):

- **Provider**: generic `OAuthProxy` + `JWTVerifier(jwks_uri=...)`.
- Same storage, signing key, transport, bearer fallback rules.
- The IdP is the OAuth server. Google (if used at all) is a
  federated upstream identity in the IdP, not the OAuth server
  seen by MCP clients. This is the line that, when crossed,
  reproduces the Authelia pain.

## Consequences

### Positive

- Every a2kit-based MCP server starts from a path that works on
  day one.
- The pitfalls we paid for are encoded in the recipe, not
  re-discovered.
- Self-hosters have a named, supported alternative without
  needing to negotiate.
- Re-validation is one document, not N codebases.

### Negative

- **The recipe will drift as FastMCP evolves.** Mitigation:
  `last_reviewed` on this ADR + a re-check when FastMCP releases
  a major version. If drift becomes routine, BACKLOG: automate a
  recipe-CI smoke test in a downstream consumer.
- **Authors who want exotic auth (mTLS, custom JWTs, multi-tenant
  per-user keys) deviate.** The recipe says how to deviate (read
  FastMCP docs, you own correctness) but does not bless those
  paths.
- **Operational dependency on a stable env-provided
  `jwt_signing_key`.** Lose the key, lose all sessions. Recipe
  doc must call out generation (`openssl rand`), storage
  (1Password / vault / `.env` outside repo), and rotation
  (sessions invalidate on rotation; acceptable for small beta).
- **Google Testing-mode 7-day expiry is a real UX cost.** If it
  becomes unacceptable before app verification clears, the bearer
  escape hatch is the documented fallback.

## References

- ADR 0010 — auth is MCP-mode only.
- ADR 0012 — deployment topology (one OAuth app per server).
- `docs/patterns/remote-mcp-access.md` — the worked-out pattern doc
  layered on this recipe.
- `examples/mcp_google_auth/` — canonical worked implementation,
  exercised by CI to catch drift against this recipe.
- FastMCP 2.13 release notes: <https://jlowin.dev/blog/fastmcp-2-13>
- FastMCP OAuth Proxy docs: <https://gofastmcp.com/servers/auth/oauth-proxy>
- FastMCP token storage deep-dive: <https://deepwiki.com/jlowin/fastmcp/7.4-token-storage-and-management>
- FastMCP issue #1649 — reactive-only refresh after restart
  (known sharp edge, harmless in practice).
- Google Testing-mode policy: <https://support.google.com/cloud/answer/15549945>
- MCP transport spec 2025-11-25: <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>
- SSE deprecation rationale: <https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/>
