---
id: "0010"
status: proposed
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [auth, mcp, cli, scope, surface]
deciders: [Denis Tomilin]
---

# ADR 0010: Authentication is an MCP-mode concern only; the CLI never authenticates

## Status

Proposed, 2026-05-18. Captures the design direction before any auth
plumbing lands in the codebase. Promote to `accepted` when the
first auth-bearing a2kit-based MCP server (knowledge-mcp) ships and
the boundary holds.

## Summary

In the context of a2kit's two transports (CLI and MCP), facing the
question of where authentication and authorization live in the
framework, we decided that auth is wired at the FastMCP server
layer in MCP mode and is not part of the CLI surface at all, and
against any cross-transport auth abstraction inside a2kit, to
achieve a transport-shaped boundary that matches how the two modes
are actually used (CLI = local single-user, MCP = remote multi-user),
accepting that operations exposed only through remote MCP become
unreachable from the CLI for users who do not run the server
locally — tracked as a separate problem (BACKLOG: remote-MCP-only
clients).

## The problem

a2kit dispatches the same tool body through two transports: CLI
(local, single-user, no network) and MCP (which today is typically
remote, multi-user, networked). The question is where auth fits.

Three shapes were on the table:

1. Auth as an a2kit primitive — every tool gets an `auth_context`
   regardless of transport; CLI synthesizes a local identity.
2. Auth as an MCP-mode concern only — the FastMCP server in front
   of a2kit handles it; a2kit core is auth-agnostic; CLI has no
   auth at all.
3. Auth as a per-tool annotation — author marks tools as `@auth_required`,
   a2kit enforces uniformly across transports.

The 2026 ecosystem shape (FastMCP 2.13+ shipping first-class auth
providers, MCP OAuth 2.1 + DCR landing in clients, no comparable
CLI auth ecosystem) makes the answer one-directional.

## What we considered (and why this one)

### Option 1: Auth as an a2kit primitive

Why it lost:

- **Forces a uniform model across asymmetric transports.** CLI
  users are local processes with filesystem access; MCP users are
  remote OAuth identities. An `auth_context` that means "the same
  thing" in both is either (a) trivially the local OS user in CLI
  mode (useless) or (b) an invented synthetic identity (a lie).
- **Couples a2kit to an auth churn surface.** OAuth specs, DCR,
  CIMD, refresh-token semantics, token storage backends — these
  change faster than a2kit can. Owning the abstraction means
  re-cutting a2kit each time the ecosystem shifts.
- **No CLI consumer asks for this.** CLI use is always single-user
  on the local machine; the OS already authenticated them.

### Option 2: MCP-mode-only auth, a2kit auth-agnostic (chosen)

The FastMCP server that hosts a2kit's MCP transport owns auth
end-to-end: provider selection (Google / generic OIDC / bearer),
token storage, refresh, beta-gating. a2kit core sees authenticated
calls arrive at its dispatcher with no auth metadata; tool bodies
receive their declared parameters and nothing else. The CLI runs
locally, opens a process for one invocation, and has no auth layer.

Why it wins:

- **Matches actual usage.** Local CLI = OS-trusted single-user;
  remote MCP = network identity. The boundary follows the network
  boundary.
- **Decouples from auth churn.** FastMCP, FastAPI middlewares,
  reverse proxies, or hosted runtimes (Cloudflare Workers, AWS
  AgentCore) can sit in front of a2kit without a2kit knowing.
  When the auth ecosystem shifts again, only the host server
  changes.
- **Keeps a2kit tools transport-clean.** A tool body that takes
  `query: str` and returns a result does not learn auth concepts
  it cannot use uniformly.
- **No abstraction to maintain.** No `auth_context` type, no
  provider plugin, no annotation. Less code, less docs, less to
  break.

### Option 3: Per-tool `@auth_required` annotation

Why it lost:

- **Annotation lifts non-uniformly.** In CLI mode it has no
  meaning. In MCP mode the FastMCP server already enforces auth
  before the dispatcher ever runs; the annotation either duplicates
  that (two enforcement points) or is decorative (lies).
- **Author confusion.** Tool authors would have to reason about
  what `@auth_required` means per transport — the exact thing
  we're trying to avoid.
- **No graceful CLI fallback.** "This tool is auth-required" in
  CLI mode would either error (breaking local single-user use) or
  silently no-op (defeating the annotation). Neither is the
  framework's call to make on the author's behalf.

## The decision

Authentication is wired in the FastMCP server that hosts a2kit's
MCP transport. a2kit core, the CLI transport, and tool bodies are
auth-agnostic.

- **CLI mode**: no auth layer. The OS trust boundary is the trust
  boundary. Tool bodies receive their declared parameters.
- **MCP mode**: the host FastMCP server owns auth (provider, token
  storage, refresh, allowlist). a2kit's MCP transport adapter
  receives already-authenticated calls and dispatches them.
- **No auth abstraction in a2kit**: no `auth_context` parameter,
  no `@auth_required` annotation, no provider plugin surface.

ADR 0011 prescribes the specific recipe for the FastMCP layer
(Google + persistent storage). a2kit ships only the docs page
showing how to compose them; the recipe lives in tool author code,
not in a2kit's source.

## Consequences

### Positive

- a2kit stays a tool-authoring framework, not an auth framework.
  The surface stops at dispatch.
- The CLI remains a thin, no-network, single-user transport — its
  speed and simplicity are preserved.
- Future MCP auth ecosystem changes (post-DCR worlds, new
  providers, gateway products) require zero a2kit changes; only
  the host server updates.
- Tool authors learn one rule: "auth is your host server's problem
  in MCP mode; CLI mode is local."

### Negative

- **Remote-MCP-only clients lose CLI access.** Some AI agents
  (Claude Desktop's web variants, ChatGPT custom connectors,
  Gemini web, web-based Claude) speak only remote MCP — they
  cannot run an a2kit CLI on the user's machine. For tools that
  matter to those agents, the CLI path is functionally invisible.
  This is a real gap. Tracked in BACKLOG as a separate problem;
  the answer is not "give a2kit cross-transport auth," it is
  "expose the relevant CLI operations as MCP tools when needed."
- **Tool authors building remote MCP servers must own auth
  themselves.** ADR 0011's prescribed recipe is the easy path,
  but they still write the wiring.
- **No framework-side enforcement of "this tool should never run
  unauthenticated."** Authors who want that guarantee must
  configure the host server, not annotate the tool.

## References

- ADR 0011 — prescribed FastMCP auth recipe for remote MCP servers.
- ADR 0012 — deployment topology (one OAuth app per server, no
  gateway).
- `docs/patterns/remote-mcp-access.md` — the worked-out pattern for
  serving web-only AI clients responsibly under this auth boundary.
- `examples/mcp_google_auth/` — canonical reference implementation.
- FastMCP auth providers: <https://gofastmcp.com/servers/auth/oauth-proxy>
- AGENTS.md — core principle "a2kit is a library, not a platform."
