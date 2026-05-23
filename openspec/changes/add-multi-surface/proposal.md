## Why

a2kit's value proposition is "write one typed function, get every transport." Today only the MCP surface delivers; the HTTP/REST surface is a 65-LOC stub serving `/health` and an empty `/openapi.json`. Without DI native to FastAPI, authors fragment to `Depends(...)` markers — splitting the authoring story. Without per-request DI scope on the HTTP path (`di-per-call-scope` says we have it; the planned HTTP path doesn't), shared SCOPED state leaks across concurrent requests on first production load. The framework already proved signature-rewriting via `install_mcp_signature`; this change generalizes that trick to make a2kit's DI work natively on both FastAPI and FastMCP via type annotation alone.

## What Changes

- **BREAKING**: Rename `src/a2kit/packages/rest.py` (stub) to `src/a2kit/packages/http/` (real FastAPI mount). Per AGENTS.md §1, the old import path raises `ModuleNotFoundError` with the new path in the message — no shim.
- **BREAKING**: Rename `build_rest_app` → `build_http_app`; `serve(..., rest=True)` kwarg → `http=True`. Loud crash on the old names.
- Generalize `install_mcp_signature` → `install_substrate_signature(fn, substrate, container)` implementing the three-way split (substrate-reserved / Container-known / wire). Frozen substrate-reserved allowlists: `{Request, Response, BackgroundTasks, WebSocket}` for FastAPI; `{Context}` for FastMCP. Extended only by ADR amendment.
- Introduce `app.api` wrapper exposing `.get/.post/.put/.delete/.patch/.options/.head` plus `app.api.fastapi_app` property accessor (lazy underlying FastAPI instance).
- Introduce `app.mcp` wrapper exposing `.tool/.prompt/.resource` plus `app.mcp.fastmcp_server` property accessor (lazy underlying FastMCP instance).
- Extend `@app.read/list/write` with `expose=("mcp","api")` kwarg (default both) and `authorize=callable` kwarg (uniform across all three families).
- Per-request DI scope on the HTTP path via `contextvars` inside the generated wrapper — not Starlette middleware. No middleware-ordering hazard.
- Auto-mount rule: each substrate sub-app builds only if it has at least one registration to expose. `build_parent_app` raises `ConfigError` if neither would mount.
- Document `container.override(T, fake)` as THE test seam for swapping a2kit-DI'd deps in FastAPI handler tests (FastAPI's `dependency_overrides[T]` does NOT work for Container-resolved types — they aren't `Depends`).
- Codemode imports SHALL be blocked under `packages/http/` via a static lint rule. The planned custom AST rule is dropped in favour of a declarative Ruff config (rationale and exact config form in design.md §D8).
- Cold-start invariant test: `import a2kit` must not transitively import `fastapi` or `fastmcp`.
- Cross-substrate smoke test: one projection tool + one `.api` route + one `.mcp.tool`, exercised on multiplexed HTTP, assert shared `Database` singleton.

## Capabilities

### New Capabilities
- `multi-surface-authoring`: Three decorator families (`@app.read/list/write` projection, `@app.api.<method>` REST-only, `@app.mcp.<feature>` MCP-only) all using one signature-rewriting mechanism to resolve a2kit DI by type annotation alone. Substrates remain native — FastAPI's OpenAPI/middleware/validation and FastMCP's Context/prompts/resources work normally.
- `substrate-signature-split`: The three-way classification — substrate-reserved (passthrough), Container-known (DI), wire (substrate-routed) — with frozen allowlists per substrate.
- `http-surface`: FastAPI mount under `/api`, auto-mounted from registrations, with per-request DI scope opened inside the generated wrapper via contextvar.
- `surface-auto-mount`: Multiplex skips substrate mounts that have zero registrations to expose; raises if neither would mount.

### Modified Capabilities
- `rest-surface`: Replaced. Today's surface is a `/health` + empty `/openapi.json` stub; new surface is a real FastAPI app generating per-tool routes from projection tools plus author-written `@app.api.*` routes. The `rest-surface` spec is rewritten in this change; future delta specs target the new `http-surface` capability.
- `serve-topology`: `build_parent_app(app, *, mcp, rest)` becomes `build_parent_app(app)` with surfaces auto-determined from registrations. `rest=` kwarg removed.
- `di-per-call-scope`: Extended to the HTTP path. Today the per-call scope is opened by the MCP dispatcher; new requirement: the HTTP wrapper opens the scope via contextvar inside its body. Same scope contract, two entry points.
- `dispatch-pipeline`: `install_mcp_signature` renamed to `install_substrate_signature` and generalized with a `substrate` parameter. Existing MCP behaviour preserved bit-exact.
- `verb-decorators`: ADD `expose=("mcp","api")` and `authorize=Callable | None` kwargs to `@app.read/list/write`. Empty `expose` raises at decoration. The existing `tags=` rejection is unchanged (author-supplied tags remain out of scope; this change does not introduce a tag-based selection surface).
- `tool-descriptors`: ADD `verb`, `expose`, and `authorize` fields to `ToolDescriptor`. Materialized at registration; immutable on the descriptor.

## Impact

**Source code**:
- New: `src/a2kit/packages/http/__init__.py`, `build.py`, `api.py`, `_scope.py`
- New: `src/a2kit/packages/mcp/surface.py` (the `app.mcp` wrapper class; existing `server.py` keeps `build_mcp_server`)
- Renamed/generalized: `src/a2kit/packages/dispatch/spec.py` (or `substrate.py`) holds `install_substrate_signature`, `split_signature`, frozen allowlists
- Modified: `src/a2kit/app.py` (adds `.api`, `.mcp` properties; `expose=`, `authorize=` kwargs on verb decorators)
- Modified: `src/a2kit/runtime.py` (tracks `api_routes`, `mcp_features` in addition to `tools`)
- Deleted: `src/a2kit/packages/rest.py` (loud `ModuleNotFoundError` on the old import path)
- Modified: `src/a2kit/packages/serve.py` (auto-mount based on registrations)

**Dependencies**:
- New: `fastapi` (lazy under `serve --transport=http`). No new transitive imports on `import a2kit` or `<app> --help`.

**Tests**:
- New: `tests/test_cold_start.py` — `import a2kit` does not load fastapi/fastmcp
- New: `tests/packages/http/test_multiplex.py` — projection + .api + .mcp.tool share Database
- New: `tests/packages/http/test_dependency_override.py` — `container.override` works; `app.dependency_overrides` doesn't
- New: `tests/packages/dispatch/test_substrate_split.py` — three-way classifier coverage
- New: `tests/packages/http/test_scope_concurrency.py` — concurrent SCOPED resolutions get different instances

**Docs**:
- New ADR 0020 (transport-profiles + multi-surface authoring; already drafted)
- Regenerate `docs/COMPONENT_MAP.md` via `scripts/component_map.py`
- Regenerate `docs/adr/INDEX.md`
- Update README to show three-decorator usage

**Consumers**:
- Existing a2kit consumers (a2web, a2atlassian, a2db, a2sdlc) currently use only `@app.read/list/write` and serve via MCP — no impact. Any consumer importing from `a2kit.packages.rest` gets a loud `ModuleNotFoundError` at startup with the new path in the message.
