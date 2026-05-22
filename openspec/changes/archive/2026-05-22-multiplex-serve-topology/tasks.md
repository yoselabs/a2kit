## 1. Dependencies

- [x] 1.1 Add `uvicorn` to `pyproject.toml` runtime dependencies; confirm Starlette is already resolvable transitively via `fastmcp`.
- [x] 1.2 Add a test asserting `uvicorn` and `a2kit.packages.rest` are absent from `sys.modules` after `import a2kit` (cold-start guard, `serve-topology` + `rest-surface` lazy-import requirements).

## 2. REST sub-application (`a2kit.packages.rest`)

- [x] 2.1 Write failing tests for `build_rest_app(app)`: returns an ASGI app; a health route under the app responds with a success status; an OpenAPI document is served whose `info` reflects `app.name` (`rest-surface` scenarios).
- [x] 2.2 Implement `a2kit.packages.rest.build_rest_app(app) -> Starlette` — a Starlette sub-app with a health route and an OpenAPI-document route (empty `paths`, `info` from `app.name`). No per-tool routes.

## 3. Lifecycle split (`_build_fastmcp_lifespan`)

- [x] 3.1 Write a failing integration test: a multiplexed server entering `async with app:` exactly once, owned by the parent; neither mount invokes `App.__aexit__`; a DI-backed tool works after full startup (`app-lifecycle` multiplexed-serve scenario).
- [x] 3.2 Split `_build_fastmcp_lifespan` in `a2kit.packages.mcp.server`: the MCP-mount lifespan keeps only `server._a2kit_app = app` and the nested user-supplied FastMCP `lifespan=`; the `async with app:` portion is removed from it.

## 4. Parent-app composition (`a2kit.packages.serve`)

- [x] 4.1 Write failing tests for the parent app: mounts MCP under `/mcp` and REST under `/api`; the parent lifespan enters `async with app:` once and forwards every mount's lifespan; a request to a DI-backed tool over `/mcp` and a request to the health route over `/api` both succeed after startup.
- [x] 4.2 Implement `a2kit.packages.serve.build_parent_app(app, *, mcp: bool, rest: bool)` — a Starlette parent app whose lifespan composes `async with app:` with each enabled mount's lifespan; mounts `build_mcp_server(app).http_app(path="/")` at `/mcp` and `build_rest_app(app)` at `/api` per the flags.

## 5. `serve` command (`a2kit.packages.mcp.cli`)

- [x] 5.1 Write failing tests for the `serve` flags: `--mcp-only` / `--rest-only` mutually exclusive (usage error when both); `--rest-only` with stdio rejected; default `--transport=http` mounts both surfaces (`serve-topology` scenarios).
- [x] 5.2 Add `--mcp-only` and `--rest-only` options to `build_serve_command`; reject the both-set and `--rest-only`+stdio combinations with a non-zero exit and a clear message.
- [x] 5.3 Rewrite the `--transport=http` branch: build the parent app via `build_parent_app(...)` with the resolved surface flags and run it under uvicorn (lazy import). Leave the stdio branch unchanged.

## 6. Verification and docs

- [x] 6.1 Run `make check`; confirm the full suite is green and coverage holds.
- [x] 6.2 Update `README.md` and `docs/VISION.md`: document `serve --transport=http` multiplexing and the `--mcp-only` / `--rest-only` flags; in VISION.md "Open questions for OpenSpec" strike the *Process model* and *Toggle shape* entries as resolved by this change.
- [x] 6.3 Add a `CHANGELOG.md` entry, noting the MCP HTTP endpoint path move to `/mcp` as a wire-path change.
