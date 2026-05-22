## Context

ADR 0010 (auth-mcp-mode-only), ADR 0011 (FastMCP Google recipe), and ADR 0012 (no gateway, one OAuth app per server) settle the auth and deployment shape for remote a2kit-based MCP servers. The `mcp-context-passthrough` capability ships the `ToolContext` Protocol that hands the live `fastmcp.Context` to verb bodies under the MCP transport. ADRs 0006 and 0009 give us composition-root re-registration and per-call DI scope. All the primitives the remote-access pattern needs already exist.

What's missing is the assembly — the documented shape of an a2kit-based MCP server that (a) extracts the authenticated user identity from the FastMCP auth layer, (b) scopes server-side state to that user, and (c) makes the right shape of operation available to web-only AI clients. Knowledge-mcp is the first downstream that needs this. Without a documented pattern, knowledge-mcp invents one, the second consumer invents a different one, and the third pays the integration cost.

Stakeholder is a single voice (Denis Tomilin / a2kit + downstream consumers). The constraint is solo cadence — pattern and example must hold for a maintainer revisiting in six months without re-deriving the rationale.

## Goals / Non-Goals

**Goals:**

- One canonical pattern doc that a downstream MCP author copies to start a Google-authenticated remote a2kit MCP that serves web-only AI clients.
- One lintable example under `examples/mcp-google-auth/` that *runs* the pattern end-to-end and is exercised by CI so a2kit-side drift fails fast.
- A liftability rubric — explicit guidance on which operation shapes lift to remote vs stay CLI-only — so authors stop one step before writing the wrong tool.
- Per-user state isolation by Google email, using only existing a2kit primitives. No new framework code.

**Non-Goals:**

- New a2kit primitives. If the pattern needs one, that's an ADR superseding 0010 or amending `mcp-context-passthrough`, not part of this change.
- Non-Google auth. The self-hosted OIDC sub-recipe in ADR 0011 is a valid deviation but not part of this pattern; it gets its own doc when a consumer needs it.
- Gateway / aggregator topology. ADR 0012 rejected it. The pattern assumes one server, one OAuth app.
- Multi-tenant beyond per-Google-user isolation. Tenant-level RBAC, shared workspaces, organization billing — out of scope.
- Lifting *every* CLI operation to MCP. The liftability rubric explicitly leaves some operations CLI-only; remote-MCP-only clients live without them, that's the deliberate trade in ADR 0010.

## Decisions

### Decision 1: Per-user `UserSession` value object provided via per-call DI

A small per-call DI factory reads the authenticated email from `ToolContext` (via FastMCP's auth state) and produces a `UserSession` dataclass with `email: str`, `workspace_dir: Path`, and any per-user state handles. Verbs that need user context declare `user: UserSession` in their signature.

**Alternatives considered:**

- *Pass `ToolContext` to every verb and let verbs read auth state directly.* Rejected: pushes auth-extraction boilerplate into every verb, makes the per-user contract implicit, and couples verb bodies to FastMCP's auth API surface (which churns).
- *A2kit-side `AuthContext` primitive parallel to `ToolContext`.* Rejected: violates ADR 0010 (a2kit is auth-agnostic) and `mcp-context-passthrough` (transport-specific state passes through, doesn't get re-modeled).
- *Synthetic `UserSession` in CLI mode too.* Rejected: the CLI has no auth (ADR 0010); fabricating an identity is a lie. CLI consumers of a verb that takes `UserSession` register a different per-call factory in the CLI composition root (e.g., reading from `$USER`) or refactor the verb to take what it needs directly.

**Rationale:** `UserSession` is example code, not framework code — it lives in the example's source tree and (later) in knowledge-mcp's source tree. Two consumers can converge on the same shape without it becoming an a2kit type. If a third consumer files friction asking for a shared `UserSession`, that's an ADR.

### Decision 2: Workspace dirs are `<root>/<sha256(email)[:16]>/`

Per-user workspace directories use a SHA-256 hash of the email (first 16 hex chars) as the directory name, not the raw email. Avoids filesystem-unsafe characters, avoids leaking PII into directory listings, and gives a stable opaque identifier.

**Alternatives considered:**

- *Raw email as directory name.* Rejected: characters like `+` and `.` are legal in emails but cause confusion in some FS contexts, and `ls` on the workspace root leaks the test-user list to anyone with read access.
- *UUIDs mapped via a sidecar table.* Rejected: adds state that has to survive restarts and stay consistent; SHA-256 of the email is deterministic and stateless.

**Rationale:** Stateless, deterministic, filesystem-safe, doesn't leak emails into directory listings. The mapping is one-way; reversibility isn't needed because the email lives in `UserSession.email`.

### Decision 3: Liftability rubric is doc-only, not framework-enforced

The pattern doc names four categories with examples — **lift** (read/search server-owned state, content generation, structured queries), **lift-with-care** (mutations on server-owned state, time-consuming operations), **don't lift** (operations on the user's local filesystem outside workspace, OS interop, opening local apps), **never lift** (anything bypassing auth, anything that escapes the workspace). The framework does not enforce these categories.

**Alternatives considered:**

- *A `@cli_only` decorator on verbs.* Rejected: pushes a transport-aware concern into verb declarations; the same verb might be liftable in one server's threat model and not another's. Author judgment, not framework rule.
- *Path-based sandboxing in a2kit core.* Rejected: a2kit doesn't own filesystem semantics. The example can ship a path guard helper, but it's example code.

**Rationale:** The rubric is for humans deciding what to write, not for runtime enforcement. Runtime enforcement requires opinions a2kit doesn't hold (what's "the workspace," what counts as "escape"). Authors who want runtime guards write them in their server.

### Decision 4: CI smoke test uses the bearer-token escape hatch

The example ships with a `make example-smoke` (or equivalent) target that boots the FastMCP server with `StaticTokenVerifier` (per ADR 0011's bearer escape hatch), issues a static test token mapped to a fixture email, and exercises one read verb + one write verb to confirm the per-user workspace contract. It does not exercise the interactive Google OAuth leg.

**Alternatives considered:**

- *Headless OAuth via a service-account token.* Rejected: Google OAuth Testing-mode doesn't grant service-account-style headless tokens for user-OAuth scopes; would require a different auth path than the recipe under test.
- *Mock the FastMCP auth provider.* Rejected: the smoke test's job is to catch real a2kit/FastMCP drift; mocking the thing under test defeats the purpose. The bearer escape hatch is real production code (it's the fallback for DCR-incompatible clients) — exercising it is legitimate end-to-end coverage of the recipe.

**Rationale:** The smoke test catches breakage at the a2kit/FastMCP/example boundary. It runs in <10s, requires no external network, and exercises the auth pathway that's actually in the recipe.

## Risks / Trade-offs

- **The pattern doc and example will drift from FastMCP / a2kit releases.** → Mitigation: CI smoke test catches breakage at framework-bump time. ADR 0011's `last_reviewed` discipline catches the recipe-doctrine side. If drift becomes routine (>1 fix per quarter), promote the example to a separately-released package with its own pin.
- **`UserSession` shape is example-private, so two consumers may diverge before convergence.** → Mitigation: the pattern doc names the minimum shape (email + workspace_dir); divergence beyond that is fine until a third consumer files friction. Convergence becomes an ADR when triggered.
- **Liftability rubric is opinion masquerading as doctrine.** → Mitigation: the rubric is illustrative, not prescriptive — the doc says "use judgment, here's how we use it." Authors can disagree and the framework doesn't care.
- **Bearer-token smoke test doesn't cover the OAuth refresh-token path.** → Mitigation: documented limitation. The refresh-token path is FastMCP's responsibility and has its own coverage upstream; if FastMCP breaks it, a2kit doesn't help and shouldn't pretend to.
- **`sha256(email)[:16]` directory naming is opaque during debugging.** → Mitigation: the example's `UserSession` stores both `email` and `workspace_dir`; verbs that need to log a human-readable identifier use `user.email`. Workspace contents include a `_email` file on first creation for forensics.

## Migration Plan

This is an additive doc + example change. No migration needed for a2kit core. On landing:

1. New files appear under `docs/patterns/` and `examples/`.
2. `BACKLOG.md` loses the two now-resolved entries.
3. Knowledge-mcp (in flight, separate repo) adopts the pattern as its first commit's reference point.
4. ADR 0010, 0011, 0012 all gain a back-reference to the new pattern doc on next ADR-index regeneration.

Rollback: delete the new files; remove the CI target; restore the BACKLOG entries. The change touches no production a2kit code, so rollback is bounded to `docs/patterns/`, `examples/`, `Makefile`, `BACKLOG.md`.

## Open Questions

- Should the example also ship a docker-compose for one-command local deploy, or keep it Python-only? Resolution: defer to implementation; if knowledge-mcp ships docker-compose, the example mirrors it for parity.
- Does the smoke test belong in the main `pytest` run or its own target? Resolution: separate target (`example-smoke`) so example breakage is visible distinctly from core test failures; main CI runs both.
- Should `UserSession` ship as a stub in a2kit's docs even though it lives in example code? Resolution: no — naming it in the pattern doc with a snippet is enough; promoting it to a docstring in a2kit core re-opens ADR 0010's boundary question.
