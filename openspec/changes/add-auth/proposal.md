## Why

Two distinct audiences need protection:

- **MCP clients** (LLMs, Claude Desktop, agentic clients) expect MCP-spec-compliant OAuth flows. FastMCP already implements them spec-correctly under the `/mcp/.well-known/*` namespace. Authors should get this by configuring a single auth wrapper on `App` — without importing from `fastmcp.server.auth.providers.*`.
- **HTTP API clients** (dashboards, ops scripts, framework consumers) want API keys — long-lived, simple to rotate, no OAuth dance for programmatic use. JWT acceptance is a secondary path for clients that already hold a token from the MCP flow.

a2kit's value here is **wrapping**, not reinventing. FastMCP's auth providers evolve with the MCP spec; forking or duplicating them is wrong. This change wraps them behind a stable `a2kit.auth.*` surface for `/mcp`, ships a minimal middleware for API keys on `/api`, and activates the `authorize=` per-tool gate that `add-multi-surface` reserved as a kwarg.

**Implementation is deferred.** This change ships **proposal.md only** so the design space is locked while higher-priority work (`add-multi-surface`, `add-tool-select`) completes. The future apply change will write `design.md`, spec deltas, and `tasks.md`.

## What Changes

- New package `src/a2kit/packages/auth/` exposing thin author-facing wrappers:
  - A `GoogleAuth(...)` wrapper around FastMCP's Google OAuth provider, so authors don't import from `fastmcp.server.auth.providers.*` directly.
  - An `APIKeyAuth(keys=...)` configuration for the FastAPI middleware. `keys` accepts an iterable or a zero-arg callable (allowing env / file / secrets-manager sourcing).
  - A `JwtAuth(jwks_url, audience, issuer)` configuration for accepting JWTs on `/api`, used when the same identities are shared between substrates.
- A `Principal` type carried in framework state (subject, scopes, claims). Whichever middleware authenticated the request populates it. The type's exact shape is locked in the apply change.
- `App.auth(spec)` registration method. Multiple calls accumulate.
- FastMCP integration: when an OAuth wrapper is registered, the wrapped provider is passed to FastMCP at `build_mcp_server` time.
- FastAPI integration: API-key and (optional) JWT middlewares are mounted on the FastAPI sub-app at `build_http_app` time. Middleware is only present when explicit auth registrations exist; no default auth.
- `authorize=` enforcement: the dispatch pipeline invokes the per-tool callable with the active principal before the tool body runs. Failed authorization raises a framework error which maps to HTTP 403 / MCP error.
- Test helper for unit-testing `authorize=` callables without spinning up middleware. Exact shape locked in the apply change.
- Cold-start invariant extension: `import a2kit` does not load auth-only dependencies.

## Capabilities

### New Capabilities

- `auth-spec`: The author-facing wrapper surface (`GoogleAuth`, `APIKeyAuth`, `JwtAuth`) and the `App.auth(...)` registration method. a2kit owns the wrappers; substrate-specific provider implementations live behind them.
- `principal-propagation`: A uniform `Principal` made available to dispatch logic regardless of which substrate authenticated the request.
- `tool-authorization`: Per-tool `authorize=` gate enforced uniformly across all dispatch surfaces. Failed authorization yields a transport-appropriate error.

### Modified Capabilities

- `multi-surface-authoring`: Activates the runtime enforcement of `authorize=` (kwarg surface already exists from `add-multi-surface`). The kwarg is reserved API surface until this change lands; enforcement turns it on.
- `http-surface`: Adds API-key and JWT validation middleware when configured. Middleware is opt-in via `App.auth(...)`; no default auth is mounted.

## Impact

This is a proposal-only change. Detailed code paths, exact module structure, dependency footprint, and test plan are deferred to the apply-cycle change which will write `design.md`, the spec deltas, and `tasks.md`. The intent of this proposal is to lock the audience model (MCP via FastMCP-native OAuth; HTTP via API keys with optional JWT SSO), the wrapper-style author surface, and the relationship to the `authorize=` kwarg reserved by `add-multi-surface`.
