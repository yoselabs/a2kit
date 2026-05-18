---
id: "0012"
status: proposed
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [auth, mcp, deployment, topology, gateway]
deciders: [Denis Tomilin]
---

# ADR 0012: MCP deployment topology — one OAuth app per server, no gateway

## Status

Proposed, 2026-05-18. Pairs with ADR 0010 (auth scope) and ADR 0011
(auth recipe). Promote to `accepted` when the second a2kit-based
MCP server (after knowledge-mcp) ships standalone and the topology
holds. Revisit when (a) the count of a2kit-based MCPs exceeds 3,
or (b) the MCP gateway ecosystem produces a stable
"Google-OAuth-fronts-N-MCPs" project.

## Summary

In the context of deploying one or more a2kit-based MCP servers
that need authentication, facing the question of whether to put
them behind an aggregator gateway or run them standalone, we
decided to ship each MCP server as a standalone process with its
own OAuth client registration (one GCP "Testing" app per server,
or one OIDC client per server in self-hosted mode), and against
adopting any current MCP gateway product to fan-in N servers
behind one OAuth gate, to achieve a topology that works today
without stacking two OAuth servers and without operating a
self-hosted IdP, accepting that users who run multiple a2kit-based
MCPs configure each server independently in their MCP client and
that we revisit if the gateway ecosystem matures or our server
count grows past ~3.

## The problem

ADR 0011 prescribes how to wire one server. The next question is
how to wire two or more. Three shapes were on the table:

1. **Aggregator gateway** — one process (MetaMCP,
   mcp-context-forge, MCPJungle, etc.) accepts the client
   connection, terminates OAuth, fans out to N backend MCPs.
2. **Standalone servers** — each MCP server runs its own process,
   its own OAuth app, its own URL. MCP clients (Claude, Cursor,
   ChatGPT) list each one independently.
3. **Reverse proxy with auth at the edge** — nginx / Caddy with a
   forward-auth middleware (oauth2-proxy, Authelia) in front of
   N MCPs that share auth state.

The temptation toward (1) and (3) comes from the intuition that
"one login should cover everything." That intuition is right in
principle and wrong in this ecosystem-year.

## What we considered (and why this one)

### Option 1: Aggregator gateway

Survey of the 2026 landscape (full notes in the
[gateway research brief](#references)):

- **MetaMCP** (2.3k stars, active) — has OIDC + API keys, but no
  documented Google connector; needs an IdP behind it.
- **IBM mcp-context-forge** (3.7k stars, active) — enterprise-
  shaped; known bugs with Entra v2; not a casual choice.
- **MCPJungle** (1k stars, active) — OSS mode lacks OIDC; you
  need enterprise mode for real auth.
- **mcpo / supergateway / mcp-proxy** — transport bridges, not
  auth aggregators.
- **mcgravity, Pluggedin-MCP** — early, small.
- **Hosted (Cloudflare Workers + Access, AWS AgentCore, Vercel)** —
  these are per-server runtimes, not multi-server fan-in.

Why it lost:

- **The protocol-fit cost is real.** MCP clients (Claude, Cursor,
  ChatGPT) probe `/.well-known/oauth-authorization-server` and try
  Dynamic Client Registration (RFC 7591). Google does not support
  DCR. A gateway either pre-registers a single OAuth client and
  loses per-user DCR semantics, or fronts Google with another OIDC
  server that does DCR — and now we have two OAuth servers stacked.
- **Authelia-in-front-of-Google was the canonical failure mode.**
  Stacking forced one of: (a) DCR direction mismatch
  (clients try to register against Google instead of Authelia
  per misconfigured `authorization_servers`), (b) 1h `id_token`
  default killing sessions, (c) loopback redirect URI port
  validation rejecting `mcp-remote` random ports,
  (d) Protected-Resource-Metadata mishandling, (e) SSE-vs-Streamable-
  HTTP transport drift. None are Authelia's fault structurally;
  they are the cost of being early.
- **No gateway product is famous or stable enough to point users
  at.** Adopting one means we own that compatibility surface for
  every MCP client release.
- **Solves a problem we don't have at our scale.** "One login for
  everything" matters when N users administer M servers with
  RBAC. With one user (Denis) and ≤3 servers, it is overhead
  without payoff.

### Option 2: Standalone servers, one OAuth app each (chosen)

Each MCP server is a separate URL, a separate GCP OAuth client (or
separate OIDC client in the self-hosted recipe), a separate token
cache. MCP clients list each in their config block.

Why it wins:

- **Works today with no gateway-ecosystem bet.** Every component is
  battle-tested standalone.
- **Aligns with how MCP clients are already designed.** Claude
  Desktop, Cursor, ChatGPT custom connectors all manage multiple
  named servers natively. The "one config block per server" UX is
  the established shape.
- **No DCR direction problem.** Each server is its own OAuth
  relying party; the FastMCP `OAuthProxy` synthesizes DCR for
  clients while holding a single pre-registered Google credential.
  This is the path FastMCP's design optimizes for.
- **Failure isolation.** A token-cache corruption, a refresh-token
  expiry, or a `jwt_signing_key` rotation on one server doesn't
  cascade.
- **Independent release cadence.** Each MCP server pins its own
  FastMCP version, GCP project, scopes.
- **OAuth app cost is bounded.** GCP Testing-mode apps are free
  and have no project-count limit that matters at our scale. The
  marginal cost of "one more GCP app" is one filled-in consent
  screen and a paste of test user emails.

### Option 3: Reverse proxy + forward-auth (oauth2-proxy / Authelia)

Why it lost:

- **Reduces to a gateway in practice.** The proxy is the OAuth
  relying party; the upstreams are protected resources. Same DCR,
  id_token-lifetime, PRM, and SSE pitfalls reappear with a
  different shape.
- **Doesn't simplify multi-server config.** Clients still see one
  endpoint and have to disambiguate which backend they want —
  which is the gateway problem under a different name.
- **Reasonable only if you already operate the proxy for other
  reasons.** Self-hosters in this position pick the self-hosted
  OIDC sub-recipe from ADR 0011 and accept that it's a real IAM
  project.

## The decision

Each a2kit-based MCP server deploys as a standalone process with
its own OAuth client. There is no recommended gateway, no
recommended forward-auth proxy, no recommended aggregator.

When a user wants to install multiple a2kit-based MCPs (e.g.
knowledge-mcp + a future skills-mcp + a future media-mcp), they
add each one to their MCP client config block individually. Each
server has its own:

- GCP project + OAuth client (Testing-mode consent screen, ≤100
  test users).
- FastMCP `GoogleProvider` instance per ADR 0011's recipe.
- Fernet-encrypted token cache on disk (separate path per server).
- `jwt_signing_key` env var (separate key per server).
- `StaticTokenVerifier` bearer escape hatch.
- URL / process / port.

The self-hosted OIDC sub-recipe (ADR 0011) is the deviation path
for users who explicitly want one IdP. In that mode the IdP is
the OAuth server; Google (if used) is a federated upstream inside
the IdP. Stacking Authelia in front of Google as the OAuth server
is the named anti-pattern.

## Consequences

### Positive

- Ships today with battle-tested components, no gateway-ecosystem
  bet.
- DCR semantics work as FastMCP designed — clients dynamically
  register against each MCP server, the server-side OAuthProxy
  handles the Google interaction with pre-registered credentials.
- Failure isolation between servers.
- Matches MCP client UX (one config entry per server).
- We can adopt a gateway later without locking in now.

### Negative

- **Each server is its own GCP app.** Operator work scales linearly
  with server count. Bounded by ADR 0010's "≤3 themed MCPs" intent.
- **Each server has its own token cache and reauth event.** When
  Google's Testing-mode 7-day expiry fires, the user reauths
  per-server. Documented; the bearer escape hatch is the fallback
  if it becomes intolerable.
- **No unified audit trail across servers.** Each FastMCP writes
  its own logs. Not load-bearing at our scale.
- **Multi-tenant scenarios (one server, many independent users
  with isolated state) are not in this topology's scope.** ADR
  0011's recipe is single-tenant-per-instance. Multi-tenant is a
  different problem.

### Re-evaluation triggers

- An a2kit-based MCP server count exceeds 3 *and* operator pain on
  per-server config becomes a filed friction.
- An MCP gateway project reaches "Anthropic recommends X" or
  "FastMCP ships first-class support for X" status with native
  Google handling.
- A multi-tenant MCP-server use case lands in our consumer set.

Any of these triggers an ADR superseding this one.

## References

- ADR 0010 — auth is MCP-mode only.
- ADR 0011 — prescribed Google + persistent-storage recipe.
- `docs/patterns/remote-mcp-access.md` — the worked-out pattern doc
  built on top of this topology.
- `examples/mcp_google_auth/` — canonical worked implementation of
  the "one OAuth app per server" shape.
- MetaMCP: <https://github.com/metatool-ai/metamcp>
- IBM mcp-context-forge: <https://github.com/IBM/mcp-context-forge>
- MCPJungle: <https://github.com/mcpjungle/MCPJungle>
- mcp-remote (client-side DCR helper): <https://github.com/geelen/mcp-remote>
- Luca Becker, "Authelia MCP OAuth gateway" (the working but
  involved self-hosted IdP recipe):
  <https://luca-becker.me/blog/mcp-oauth-gateway-authelia/>
- WorkOS, "Dynamic Client Registration in MCP OAuth":
  <https://workos.com/blog/dynamic-client-registration-dcr-mcp-oauth>
- Permit.io, "OAuth on MCP guide":
  <https://www.permit.io/blog/oauth-on-mcp>
