## Why

`serve` today runs exactly one surface: `build_mcp_server(app).run(transport=...)` over stdio or MCP-over-HTTP. VISION.md commits a2kit to a REST surface and frames two unresolved questions — the **process model** (one process multiplexing all surfaces vs process-per-surface) and the **toggle shape** (how an operator turns a surface off). A REST surface cannot be bolted on coherently until those are decided: it needs a place to be mounted, a lifecycle that does not fight MCP's, and a command grammar to select it. This change builds that container so the REST tool-route projection can drop into it cleanly.

## What Changes

- `serve --transport=http` becomes a **multiplexed server**: one process, one port, an a2kit-owned parent ASGI (Starlette) app that mounts each surface as an independent sub-app — `/mcp` for the FastMCP sub-app, `/api` for the REST sub-app.
- The MCP-over-HTTP path moves from `FastMCP.run(transport="http")` to `parent.mount("/mcp", build_mcp_server(app).http_app())`, run under uvicorn. Local stdio (`serve` with no `--transport`) is unchanged.
- **The a2kit `App` lifecycle is owned by the parent app.** A single `async with app:` spans the whole process; each mount carries only its transport-specific lifespan (FastMCP's session manager), forwarded to the parent. This removes the shutdown-coupling hazard where one surface's exit drains the shared DI container out from under the other.
- New surface-selection flags on `serve`: `--mcp-only` and `--rest-only`, mutually exclusive, both default off (= all surfaces on, per VISION principle 1). `--rest-only` combined with stdio is rejected — REST cannot ride a single-protocol pipe.
- A **minimal REST surface** ships so the second mount is real and testable: a health route and an OpenAPI document. Per-tool REST route projection (verb→method routing, `Accept`-header content negotiation) is explicitly **deferred** to a follow-on `add-rest-surface` change.
- The Starlette REST sub-app reuses a dependency already present transitively via FastMCP — no new top-level dependency. The REST-framework decision (FastAPI vs Starlette vs hand-rolled) is deferred with the projection work.

## Capabilities

### New Capabilities

- `serve-topology`: the multiplexed `serve` model — parent ASGI app, per-surface mounts, one process / one port under `--transport=http`, and the `--mcp-only` / `--rest-only` selection grammar.
- `rest-surface`: the REST surface as a mounted ASGI sub-app. This change establishes only its minimal slice — a health route and an OpenAPI document; per-tool route projection is a later requirement on this same capability.

### Modified Capabilities

- `app-lifecycle`: a multiplexed server SHALL enter the `App` lifecycle exactly once for the process, owned by the parent app, not once per mounted surface.

## Impact

- **Code**: `src/a2kit/packages/mcp/cli.py` (`serve` command — flags, multiplex branch); `src/a2kit/packages/mcp/server.py` (`_build_fastmcp_lifespan` splits — App-lifecycle part hoists to the parent, session-manager part stays); a new `a2kit.packages.serve` (parent-app composition) and `a2kit.packages.rest` (minimal REST sub-app) module.
- **Dependencies**: uvicorn becomes a `serve`-path runtime dependency (lazily imported, not at `import a2kit` — VISION principle 6). No new dependency for the REST sub-app itself (Starlette is already transitive via FastMCP).
- **Behaviour**: `serve --transport=http` now also serves `/api` (minimal) alongside `/mcp`. The MCP endpoint path changes from the FastMCP default root to `/mcp` — noted as a wire-path change for HTTP MCP clients.
- **Docs**: VISION.md "Open questions for OpenSpec" — the *Process model* and *Toggle shape* entries are resolved by this change and struck on archive.
