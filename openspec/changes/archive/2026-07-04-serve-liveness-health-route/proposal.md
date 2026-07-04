## Why

`serve --transport=http` builds an a2kit-owned Starlette parent
(`packages/serve.py:build_parent_app`) that mounts each *populated* surface
at `/{surface.name}`. The only liveness route today lives **inside** the
FastAPI sub-app (`packages/http/build.py:105`, `@app.get("/health")`), so it
is served at `/api/health` — and only when the `api` surface has
registrations. An MCP-only deployment (`serve --transport=http
--select surface=mcp`) mounts `/mcp` alone and therefore exposes **no
liveness route at all**:

```
serve --transport=http                       → /mcp + /api/health   (probe ✓)
serve --transport=http --select surface=mcp  → /mcp ONLY            (NO liveness ✗)
```

`/mcp` is not a substitute: a bare `GET /mcp` needs the streamable-HTTP
handshake (`Accept: text/event-stream` / session) and returns 4xx/406, so
`curl -f` fails against a perfectly healthy server. A container `HEALTHCHECK`
/ k8s liveness probe has nothing to hit.

Liveness is a **transport concern** — it belongs in the substrate, not in a
web-fetching domain or coupled to the `api` surface being enabled. This is an
outgoing wish from a2web (`docs/history/A2KIT_FEEDBACK_v0.47.md`, round 15);
a2web's `deployable-container-ci` change is blocked on it and is running an
explicit retire-on-a2kit-fix interim (attaching the route through the
`fastmcp_server` escape hatch — domain code owning a transport concern).

## What Changes

- **Register a static root `/health` liveness route on the multiplex parent**
  (`build_parent_app`) so that *any* HTTP serve — MCP-only included — exposes
  a stable, cheap `GET /health → 200 {"status": "ok"}`. Surface-agnostic:
  present whenever at least one surface is mounted over HTTP, regardless of
  which surfaces those are.
- **Keep it dumb.** Static 200, no DI resolution, no surface forwarding — a
  wedged DI graph MUST still answer liveness. Readiness/degraded aggregation
  stays on the existing `_meta.health` MCP tool (this capability's other
  requirements).
- **Additive / back-compatible.** The existing `/api/health` on the FastAPI
  sub-app stays for REST deployments; no behavior change for servers that
  already mount `/api`.
- **(Optional, additive)** also register a FastMCP `custom_route("/health")`
  inside `build_mcp_server`, so the bare `build_mcp_server(...).http_app()`
  path (no parent) also carries liveness at `/{mount}/health`. Not required to
  unblock a2web (which serves through the parent); decided in tasks.

## Capabilities

### Modified Capabilities

- `health-probe`: adds a **transport-native liveness route** requirement —
  every HTTP serve exposes a dumb, auth-free root `/health` independent of
  which surfaces are mounted. This is the liveness counterpart to the
  capability's existing readiness (`_meta.health`) and CLI-exit-code
  requirements.

## Non-goals

- **Not** changing `_meta.health` readiness semantics or the `<app> health`
  CLI. Liveness and readiness stay separate by design.
- **Not** fixing the latent `APIKeyAuth` non-exemption of `/api/health` (see
  design → Auth). Called out, scoped out; the new root route is auth-free by
  construction and does not depend on that fix.
- **Not** a2web-side work (Dockerfile `HEALTHCHECK`, dropping the interim
  escape-hatch). That lands in a2web's `deployable-container-ci` once this
  ships.
