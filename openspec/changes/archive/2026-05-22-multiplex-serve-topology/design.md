## Context

`serve` (`a2kit.packages.mcp.cli.build_serve_command`) runs one surface: `build_mcp_server(app).run(transport="stdio"|"http")`. The HTTP branch hands the whole process to FastMCP — FastMCP owns the Starlette app, the uvicorn run, and the lifespan.

VISION.md commits to a REST surface and leaves two questions open: **process model** and **toggle shape**. The `/opsx:explore` session that produced this change resolved both, and corrected a misread of the `App` lifecycle along the way:

- `App.__aenter__` (app.py:445-462) seals (idempotent) and calls `Container.__aenter__` (container.py:429-439), which only re-seals. There is **no eager resource entry** — v0.36 `di-scoped-lifecycle` made App-scope resources and routers enter lazily on first dispatch.
- Therefore a double `__aenter__` is harmless. The hazard is the **exit**: the DI container and its cleanup stack live on the single `App`. If two mounts each owned `App.__aexit__`, whichever surface shut down first would drain the shared container while the other surface was still serving.

FastMCP 3.2's `create_streamable_http_app` returns a Starlette app whose `lifespan` does *required* setup (`StreamableHTTPSessionManager`, `session_manager.run()`, `server._lifespan_manager()`). A Starlette `Mount`ed sub-app's lifespan does **not** run unless the parent forwards it.

## Goals / Non-Goals

**Goals:**

- One process, one port under `serve --transport=http`, serving MCP and REST from independent mounts.
- Single, parent-owned `App` lifecycle — no shutdown coupling between surfaces.
- An operator grammar to run a single surface: `--mcp-only` / `--rest-only`.
- A real, testable REST mount — enough to prove the multiplex end to end.
- Keep `import a2kit` cold-start clean: uvicorn and the REST module load only on the `serve` path.

**Non-Goals:**

- Per-tool REST route projection — verb→HTTP-method routing, OpenAPI route entries, `Accept`-header content negotiation. Deferred to `add-rest-surface`.
- The REST-framework decision (FastAPI vs Starlette vs hand-rolled). The minimal slice uses Starlette directly; the choice is made when projection lands.
- Per-tool surface opt-out (a `visibility` fourth value, "never REST"). Server-level flags are sufficient here; the per-tool axis is a separate ADR.
- REST auth. Remote REST is multi-user and must authenticate; that is `add-rest-surface` scope.
- Changing local stdio `serve`.

## Decisions

### D1: Parent ASGI app mounts independent sub-apps (Shape B)

a2kit owns a top-level Starlette app. It mounts `/mcp` → `build_mcp_server(app).http_app(path="/")` and `/api` → the REST sub-app. uvicorn runs the parent.

*Alternative — Shape A* (REST rides inside FastMCP's app via `@custom_route`) was rejected: REST becomes a structural guest, `--rest-only` would still construct a FastMCP server just to borrow its Starlette app, and auth/lifespan are FastMCP-shaped. Shape B keeps each surface an independent projection of the one tool catalog — consistent with how the CLI and MCP adapters already relate to `App`.

### D2: The parent app owns one `async with app:`

The parent app's lifespan enters `async with app:` exactly once for the process. Each mount's lifespan covers only transport-specific setup. `_build_fastmcp_lifespan` (server.py:129-150) splits:

- **stays** with the MCP mount: setting `server._a2kit_app = app` and nesting any user-supplied FastMCP `lifespan=`. FastMCP's own session-manager lifespan is untouched.
- **hoists** to the parent: `async with app:`.

Both mount lifespans are composed into the parent lifespan and forwarded (the Starlette `Mount`-lifespan rule). Enter order does not matter (entry is lazy + idempotent); single exit ownership is the property that does.

*Alternative — each mount enters the App* was rejected for the shutdown-coupling bug above. *Alternative — make `App.__aexit__` idempotent and let both call it* still leaves the temporal hazard (surface A drains resources while surface B serves) and is not a real fix.

### D3: `--mcp-only` / `--rest-only`, mutually exclusive, default off

Both flags default off → all surfaces on (VISION principle 1: opt-out, never opt-in). Passing both is a usage error. `--rest-only` with stdio (or `serve` with no `--transport`) is rejected: REST cannot multiplex onto a single-protocol stdio pipe. `--mcp-only` with stdio is accepted and redundant.

*Alternative — `--without=`* (negation) and *`--surfaces=` list* were considered in the explore session; the paired intent flags read the most naturally for the current two-surface world. Accepted trade-off: the form does not compose to a third non-MCP surface — if one ever lands, migrate to `--surfaces=`.

Code execution stays on its existing `--code-mode-off` / `--code-mode-allow-destructive` flags, nested under MCP. `--rest-only` makes them inert (no MCP server is built); this is allowed, not an error.

### D4: Minimal REST surface — health route + OpenAPI document

`a2kit.packages.rest` exposes `build_rest_app(app) -> Starlette`. This change ships only: a health route and an OpenAPI document (an empty-paths skeleton with `info` from `app.name`). It is a complete vertical slice — parent app, two real mounts, flags, lifecycle — without claiming routes it does not serve. Per-tool route projection is the first follow-on requirement on the `rest-surface` capability.

### D5: uvicorn is a lazy `serve`-path dependency

uvicorn moves into the dependency set but is imported only inside the multiplex branch of `serve`, never at `import a2kit` (VISION principle 6). The REST sub-app uses Starlette, already transitive via FastMCP — no new top-level dependency for it.

## Risks / Trade-offs

- **Mount-lifespan not forwarded → singletons never enter, silently** → the parent lifespan explicitly composes and awaits every mount's lifespan; an integration test asserts a DI-backed tool works over both `/mcp` and `/api` after a full startup.
- **MCP HTTP endpoint path moves** from FastMCP's default to `/mcp` → documented as a wire-path change; the explore session noted no external HTTP MCP consumers today.
- **A multiplex parent with one near-empty mount looks like premature structure** → mitigated by D4: the REST mount serves a real health route and OpenAPI doc, and the lifecycle/flags work is only coherent with two surfaces present. The change is the smallest shape that is internally consistent.
- **uvicorn in the dependency tree** → accepted; lazily imported, `serve`-path only, consistent with FastMCP's existing confinement.
- **`--mcp-only`/`--rest-only` does not scale past two surfaces** → accepted and documented; migration path to `--surfaces=` is noted.

## Migration Plan

1. Land `a2kit.packages.serve` (parent-app composition) and `a2kit.packages.rest` (`build_rest_app`).
2. Split `_build_fastmcp_lifespan`; the MCP mount keeps the back-reference + user-lifespan nesting only.
3. Rewrite the `serve --transport=http` branch to build the parent app and run it under uvicorn; add the flags.
4. stdio `serve` is untouched — no rollback concern there. The HTTP branch is the blast radius; rollback is reverting the `serve` command factory.

## Open Questions

- The exact OpenAPI `info`/`servers` content for the skeleton — settled in the specs phase; it does not affect topology.
- Whether `/api` is the right default REST prefix or it should be operator-configurable — defaulted to `/api` here; revisit if `add-rest-surface` needs versioned prefixes (`/v1`).
