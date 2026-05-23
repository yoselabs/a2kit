## Context

a2kit is a Python framework that exposes typed tool functions over multiple transports (CLI, MCP, HTTP). The current shape (post-architecture wave 2, ADR 0019):

- `App` is the compose-phase builder. `build(app) -> AppRuntime` produces a sealed runtime.
- `build_mcp_server(runtime)` builds a FastMCP app whose tool handlers are signature-rewritten by `install_mcp_signature` — DI params are stripped from the surface-facing signature; the wrapper opens `Container.call_scope` and resolves DI.
- `build_rest_app(runtime)` is a 65-LOC stub serving `/health` and an empty `/openapi.json`.
- `build_parent_app(app, *, mcp, rest)` mounts both under a single Starlette parent for `serve --transport=http`.
- The lazy-import discipline keeps `fastapi`, `fastmcp`, `typer` out of `import a2kit` and `<app> --help`.

The signature-rewriting trick is the load-bearing precedent — proven, in production, well-tested. This change generalizes it.

The review surfaced four critical fixes that shape this design: (1) substrate-reserved type passthrough, (2) per-request scope via contextvar (not middleware), (3) `container.override` as the test seam, (4) `--select 'surface=...'` for disabling surfaces (this last lives in `add-tool-select` — referenced here for completeness).

## Goals / Non-Goals

**Goals:**

- Three decorator families on `App`, all driven by **one** signature-rewriting mechanism.
- a2kit DI resolves by type annotation alone on both substrates — no `Depends(...)` in author code.
- FastAPI sees native handlers; OpenAPI, middleware, validation, and `app.api.fastapi_app.add_middleware(...)` all work without a2kit interposing at runtime.
- FastMCP sees native handlers; Context, prompts, resources, sampling all work; existing MCP behaviour preserved bit-exact.
- Per-request DI scope on the HTTP path with identical contract to the existing MCP per-call scope (ADR 0009 / `di-per-call-scope`).
- Auto-mount: substrate sub-apps build only when registrations exist for them.
- Cold-start: `import a2kit` and `<app> --help` do not load `fastapi` or `fastmcp`.
- `container.override(T, fake)` is the test seam; documented loudly.

**Non-Goals:**

- `--select` DSL or surface-disable filter (see `add-tool-select`).
- Authentication (see `add-auth`, proposal-only).
- Dashboard / web UI surface (deferred until a real consumer exists).
- `Router` class for tool grouping (deferred until empirical >20-tool demand).
- CEL expressions for selectors (deferred).
- Surface enable/disable CLI flags (replaced by `--select 'surface=...'`).
- Backwards-compatibility shims for `a2kit.packages.rest` (loud crash per AGENTS.md §1).
- Type-injection by Container for FastAPI-native primitives (`Request`, `Response`, etc.) — those stay substrate-owned.

## Decisions

### D1. Three-way signature split (substrate-reserved / Container-known / wire)

The rewriter classifies each parameter into exactly one bucket:

1. **Substrate-reserved** — type matches a frozen allowlist; param passes through to the substrate-facing wrapper signature. The substrate populates it at dispatch.
2. **Container-known** — `container.has_provider(type)` is true; the wrapper resolves via `Container.call_scope`.
3. **Wire** — anything else; substrate routes it from request body/query/path/form.

Frozen allowlists (extended only by ADR 0020 amendment):

```python
_FASTAPI_RESERVED: frozenset[type] = frozenset({
    starlette.requests.Request,
    starlette.responses.Response,
    fastapi.BackgroundTasks,
    starlette.websockets.WebSocket,
})

_FASTMCP_RESERVED: frozenset[type] = frozenset({
    fastmcp.Context,
})
```

**Alternatives considered:**

- *Annotation-marker discipline (`Inject[T]`, `Wire[T]` markers)*: rejected — defeats the "type annotation alone" goal.
- *Heuristic classification (e.g., "if a `BaseModel`, it's wire")*: rejected — fragile, ambiguous when a Container provides a pydantic model.
- *Two-bucket split treating substrate-reserved as wire*: rejected — FastAPI would try to model `Request` as a request-body field; FastMCP would expose `Context` in tool schemas. Both wrong.

The allowlist approach is structural and explicit. Adding a new reserved type is an ADR amendment plus a one-line frozenset extension.

### D2. Per-request DI scope via contextvar inside the wrapper

The HTTP per-request DI scope is opened **inside the generated wrapper** body, using a `contextvars.ContextVar` named `_a2kit_scope`. The wrapper enters `Container.call_scope(fn, wire_kwargs)` as an async context manager, sets the scope token on the contextvar before invoking `fn`, and resets the token in `finally` — symmetric with the existing MCP path. Implementation details live in tasks 1.4–1.5.

**Why not Starlette middleware:**

- Middleware ordering matters — a wrong-order middleware (e.g., auth before scope) would see no scope; right order is brittle to add.
- Middleware runs once per request; per-tool overrides become awkward.
- contextvar inside the wrapper is local, ordering-independent, and matches the MCP path's pattern (also wrapper-local).

**Alternatives considered:**

- *Starlette middleware that opens scope and stores token on `request.state`*: rejected — middleware ordering hazard, less symmetric with MCP path.
- *FastAPI dependency (`Depends(open_scope)`)*: rejected — pollutes author signatures with `Depends`, defeating D1.

### D3. Test seam: `container.override`, not `app.dependency_overrides`

FastAPI's `dependency_overrides[T]` keys on `Depends` callables. a2kit-DI'd types are not `Depends`. Therefore `dependency_overrides[Database] = fake_db` will not swap a2kit-resolved `Database`. The test seam is:

```python
async with app.runtime.container.override(Database, fake_db):
    response = await client.post("/api/fetch", json={"id": "x"})
```

`app.dependency_overrides` continues to work for any explicit `Depends(...)` an author chose to write inside `@app.api.*` (rare but possible).

**Alternatives considered:**

- *Auto-bridge a2kit Container into FastAPI's `dependency_overrides`*: rejected — leaky and surprising; FastAPI's mechanism is for `Depends` callables, not type-driven DI.
- *Provide a sugar `app.override(T, fake)`*: noted as a future ergonomic improvement; not required for v1.

This is the single biggest user-reported friction risk; the proposal documents it in README and the smoke test docstring.

### D4. Auto-mount based on registrations

Substrate sub-apps build only if registrations exist:

```python
def build_parent_app(app: App | AppRuntime) -> Starlette:
    runtime = build(app)
    mounts = []
    if _has_api_registrations(runtime):
        mounts.append(("/api", build_http_app(runtime)))
    if _has_mcp_registrations(runtime):
        mounts.append(("/mcp", build_mcp_server(runtime).http_app(path="/")))
    if not mounts:
        raise ConfigError("No surfaces have registrations to expose.")
    return _starlette_parent(mounts, runtime)
```

Counters: `_has_api_registrations` returns true if any tool has `"api" in expose` OR any author-written `@app.api.*` route exists. `_has_mcp_registrations` is the dual. `--select 'surface=...'` (separate change) post-filters and may zero out a counter.

**Alternatives considered:**

- *Explicit `serve --mcp --api` flags*: rejected — too many flags, redundant with the registration signal, and `--select 'surface=...'` covers the deploy-time override case structurally.
- *Always build both substrates, return 404 on the empty one*: rejected — wasteful cold-start when only one is in use.

### D5. Named substrate accessors (`fastapi_app`, `fastmcp_server`), not `.raw`

```python
app.api.fastapi_app.add_middleware(GZipMiddleware)
app.mcp.fastmcp_server.add_middleware(LoggingMiddleware())
```

**Rationale:**

- Self-documenting — the property name tells you what type comes back.
- Honest — it's the substrate instance, no a2kit wrapper.
- Symmetric across both surfaces.

**Alternatives considered:**

- *`.raw`*: rejected — short but undescriptive; "raw what?" requires reading code.
- *No accessor (expose only via subclassing)*: rejected — escape hatch for middleware is common enough to deserve a documented attribute.

### D6. `expose=` and `authorize=` kwargs on projection decorators

```python
@app.read   async def fetch(*, id, db: Database) -> Memory: ...   # both substrates
@app.read(expose=["mcp"])  async def llm_only(...): ...           # MCP only
@app.list(expose=["api"])  async def admin(...): ...              # REST only
@app.write(authorize=admin_only)  async def upsert(...): ...      # gate
```

Default `expose=("mcp", "api")`. `authorize=` accepts `Callable[[Principal, ToolDescriptor, dict], bool | Awaitable[bool]]`. Empty default (no gate).

**Why a kwarg, not a separate decorator:**

- One bit of state per concern — kwargs match the granularity.
- Composes with FastAPI/FastMCP-native decorator kwargs without a stacking surface.
- `@app.authorize` decorator would add a vocabulary item without saving a line.

`authorize=` is also accepted by `@app.api.*` and `@app.mcp.*` for symmetry. Auth implementation lands in `add-auth` (proposal-only); the kwarg surface lands here so authors don't have to refactor signatures later.

### D7. Rename `packages/rest.py` → `packages/http/`, loud crash

Per AGENTS.md §1, no shims. **Decision: delete `packages/rest.py` outright.** Python's native `ModuleNotFoundError: No module named 'a2kit.packages.rest'` satisfies the loud-crash requirement; the new path is named in the consumer's traceback. No sentinel stub is shipped (sentinels add a maintenance edge for no benefit — the message is the same whether Python emits it or a custom raise emits it).

### D8. Replace planned custom lint rule with Ruff config

The planned `A2K-PROFILE-CAP` AST rule (forbid `codemode` imports under `packages/http/` and `packages/auth/`) is replaced by Ruff's `flake8-tidy-imports.banned-module-level-imports` config in `pyproject.toml`:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
# (declarative; matches the prior intent)

[tool.ruff.lint.per-file-ignores]
# (per-path overrides where needed)
```

Saves the AST rule's LOC + maintenance. The existing `A2K-LAYER` rule already enforces the directional discipline at a higher level.

### D9. The `App` attribute shape

```python
class App:
    @property
    def api(self) -> "ApiSurface":  # lazy: imports `fastapi` only on first access
        if self._api is None:
            from a2kit.packages.http.api import ApiSurface
            self._api = ApiSurface(self)
        return self._api

    @property
    def mcp(self) -> "McpSurface":  # lazy: imports `fastmcp` only on first access
        if self._mcp is None:
            from a2kit.packages.mcp.surface import McpSurface
            self._mcp = McpSurface(self)
        return self._mcp
```

Touching `app.api` or `app.mcp` pulls the substrate in lazily. `import a2kit` and `<app> --help` never touch these properties.

## Risks / Trade-offs

- **Substrate feature drift.** FastAPI or FastMCP may add a new type-injected primitive (similar to `BackgroundTasks`). → Mitigation: substrate-reserved allowlist is a frozenset with ADR-amendment-only extension; new entries require ADR 0020 amendment with a one-line code change. Detected by an integration test asserting the allowlist set matches a known-good baseline.

- **OpenAPI schema fidelity.** The generated FastAPI handler has a stripped signature; if a user wants to post-process the OpenAPI doc, they drop to `app.api.fastapi_app` and FastAPI's own override machinery. → Acceptable trade-off; the 95% case generates the right doc automatically.

- **Author confusion about `dependency_overrides` not working.** → Mitigation: documented in README, in the smoke test docstring, and in a dedicated `tests/packages/http/test_dependency_override.py` showing both the failure and the correct `container.override` pattern.

- **Cold-start regression.** A future contributor might add a top-level `import fastapi` to `packages/http/__init__.py`. → Mitigation: `tests/test_cold_start.py` asserts `import a2kit` does not load `fastapi` or `fastmcp`. Plus the existing `A2K-LAYER` discipline keeps HTTP in L5.

- **Per-request scope contextvar leaks.** If the `finally` is skipped (e.g., generator exit corner case), the scope token could leak. → Mitigation: the contextvar's value is the Scope itself; `Scope.__aexit__` (already in DI plumbing) cleans deterministically via the AsyncExitStack. The token is only the contextvar-set marker, which `reset()` undoes; leaking it does not leak the Scope's resources.

- **`expose=` mis-configuration.** Author writes `expose=["mcp"]` and forgets to also write `@app.api.*` routes for any REST functionality; serving `--transport=http` finds zero API registrations and skips the mount. → Acceptable; the auto-mount rule makes this self-documenting. Operator sees `/api/*` returns connection-refused (or 404 from Starlette fallthrough); root cause is the empty registration set, easy to diagnose.

- **Auth gate runs per dispatch.** `authorize=` callable is invoked on every call. If the callable does expensive work (DB lookup of role), every dispatch pays for it. → Documented in the eventual `add-auth` design: "make `authorize` fast; cache inputs you control"; framework does not silently memoize because security decisions should not be cached without explicit author intent.

## Migration Plan

1. Land the substrate splitter generalization first (Phase 1 in tasks.md). Existing MCP tests must pass byte-for-byte — the rename + generalization is mechanical.
2. Add `packages/http/` package and `build_http_app` (Phase 2). At this point, multi-surface registrations don't exist yet but the substrate is ready.
3. Add `App.api` and `App.mcp` properties + projection `expose=`/`authorize=` (Phase 4 — depends on Phases 2 and 3).
4. Delete `packages/rest.py`. Any consumer importing from it gets a loud `ModuleNotFoundError` at startup. No rollback needed — consumers update one import line.
5. Update README + tutorial in the same PR/commit so the documented patterns match the new surface.

**Rollback:** Revert the change as a single commit. Consumers who haven't migrated their imports are unaffected. Consumers who already migrated re-add the `rest` → `http` import — one-line revert per consumer.

## Open Questions

- **Where exactly does `authorize=` run in the dispatch pipeline?** Before format routing, after wire validation. To be pinned in `add-auth` design; this change reserves the kwarg surface but does not implement enforcement.
