# Design — transport-native liveness route

## Context

The wish (`A2KIT_FEEDBACK_v0.47.md`) proposes a FastMCP
`custom_route("/health")` inside `build_mcp_server`. Grounding it in the code
surfaced a path mismatch that reshapes the fix, and settled the auth question
the wish asked us to confirm.

## Topology (verified)

```
build_parent_app (a2kit-owned Starlette parent)   ← no auth middleware here
├── Mount("/api")  → FastAPI sub-app               ← auth installed inside sub-app
│     └── GET /health {"status":"ok"}              ← the only liveness route today
└── Mount("/mcp")  → FastMCP .http_app()           ← FastMCP's own auth inside
      └── POST /mcp (JSON-RPC, needs SSE handshake)

--select surface=mcp  ⇒  only the /mcp Mount  ⇒  NO /health
```

## The decision: root `/health` on the parent (not `custom_route` in the MCP app)

A FastMCP `custom_route("/health")` registered in `build_mcp_server` lands at
**`/mcp/health`** once the parent mounts the MCP surface at `/mcp` — *not*
`/health`. a2web's `deployable-container-ci` hardcodes its probe as
`curl -f http://localhost:<port>/health` (a **root** path, tasks 2.5 / 3.3).
So the wish's primary implementation would ship a path a2web does not probe.

| Option | Path (through parent) | Verdict |
|---|---|---|
| A — `custom_route` in `build_mcp_server` | `/mcp/health` | Wrong path for a2web; only present when MCP is served |
| **B — root `/health` on `build_parent_app`** | **`/health`** | **Surface-agnostic; auth-free by construction; matches a2web exactly** ★ |
| C — both A + B | both | A only adds value on the no-parent `build_mcp_server(...).http_app()` path |

**Chosen: B.** `build_parent_app` *is* a2kit's transport-multiplex layer — the
one component that knows "we are serving HTTP" and is surface-agnostic. A
static route there:
- is present whenever **any** surface is served over HTTP (MCP-only, api-only,
  both);
- emits exactly the `/health` a2web's `HEALTHCHECK` probes;
- is **auth-free by construction** (below);
- touches no DI, so a wedged graph still answers — the wish's "dumb liveness"
  intent.

No forwarding to a surface's health: forwarding would re-couple liveness to
surface state, which defeats "liveness is dumb." Readiness stays on
`_meta.health`.

Option **A is offered as an optional additive task** so the bare
`build_mcp_server(...).http_app()` composition (no parent) also carries
liveness. It is not required to unblock a2web.

## Auth — resolved (the wish asked us to confirm)

| Route | Behind auth? | Why |
|---|---|---|
| FastMCP `custom_route` → `/mcp/health` | No, exempt | `auth.get_middleware()` returns only `AuthenticationMiddleware` + `AuthContextMiddleware` (populate context, never reject). The rejecting `RequireAuthMiddleware` wraps **only** the `/mcp` endpoint, not custom routes. |
| **Parent root `/health`** | **No, exempt by construction** | All auth middleware is installed **inside** each sub-app. The parent Starlette has none; a parent-level route is a sibling to the mounts, never wrapped. |
| Existing `/api/health` | ⚠️ **Behind auth today** | `APIKeyAuth.build_middleware` (`auth/api_key.py:73`) 401s **every** HTTP scope with no path exemption. |

The wish's premise — "the analog of how `/api/health` should be reachable
without an API key" — is **false for the api-key strategy**: today
`/api/health` returns 401 without a key when `APIKeyAuth` is configured.
"Do what `/api/health` does" would inherit that latent bug. The parent-root
route sidesteps it entirely: auth-free by construction regardless of what any
surface configures.

**The `/api/health` non-exemption is a real, separate bug — scoped out of this
change** (Non-goals). Folding an exempt-liveness-path into the auth middleware
is its own concern; this change does not depend on it.

## Relationship to `_meta.health` (readiness — already core + multi-surface)

a2kit already owns a health probe: `_meta.health` (`packages/health`). It is
core and multi-surface — a projection tool stamped LISTED on every surface, so
it is reachable as an MCP tool, as `POST /api/_meta.health`, and as the
`<app> health` CLI exit code. This change does **not** touch it.

`_meta.health` is **readiness**, not liveness, and cannot serve as the probe:

| | `_meta.health` (readiness) | new root `/health` (liveness) |
|---|---|---|
| Exists | only if ≥1 `@app.health_check` registered | always, on any HTTP serve |
| Access | MCP session handshake / `POST` body | plain unauthenticated `GET` |
| Payload | rich `{status, version, checks}`, can be `degraded` | static `{"status":"ok"}`, always 200 |
| MCP-only serve | `/api/_meta.health` route gone; MCP tool needs a session | present at `/health` |
| Purpose | "is the app's work healthy" | "is the process alive and routing" |

The two are the standard liveness/readiness split. The root `/health` is, if
anything, *more* faithful to "health is core regardless of surface" than
`_meta.health`: it sits **above** every surface on the parent, not replicated
onto each one, so it cannot be dropped by any surface selection.

## stdio

Liveness is HTTP-only; stdio's liveness is process-alive over the pipe. The
parent app is HTTP-only, so the fit is clean — no stdio work.

## Relationship to the refounding (ADR 0032)

`refound-a2kit-as-fastmcp-helpers` will eventually delete `App` /
`build_parent_app` and have consumers compose FastMCP directly. This route is
deliberately scoped to the **current** substrate that a2web depends on today.
When the refounding lands and the parent is removed, liveness migrates to a
FastMCP `custom_route` in the consumer's own direct composition (mounting the
FastMCP app at root, where `custom_route("/health")` naturally resolves to
`/health`) — exactly the wish's idiom, in the place it then belongs. The fix
is honest about its lifespan: a small additive route on the framework-era
parent, superseded by the helper model rather than fighting it.

## Route placement details

- Add a `starlette.routing.Route("/health", _live, methods=["GET"])` to the
  `routes=[...]` list in `build_parent_app`, alongside the `Mount`s. Mounts are
  prefix matches at `/api` / `/mcp`; `/health` does not collide.
- Handler: `async def _live(_request) -> JSONResponse` returning
  `{"status": "ok"}`, 200. No runtime/DI access — matches the `/api/health`
  contract byte-for-byte.
- The route is added unconditionally whenever `build_parent_app` produces a
  parent (i.e. at least one surface has registrations); the existing
  `ValueError` on zero surfaces is unchanged — a server with nothing to serve
  still fails fast.
