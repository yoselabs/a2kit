# Tasks — lifespan over lifecycle hooks

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` + `make lint` green. (797 baseline)
- [x] 0.2 Inventory every `@on_startup` / `@on_shutdown` call site
      across `src/`, `tests/`, and `examples/`:
      - 0.2.a `src/a2kit/app.py` — registry methods, dispatchers
      - 0.2.b `src/a2kit/packages/cli/runtime.py` — dispatch_startup/shutdown
      - 0.2.c `src/a2kit/packages/mcp/server.py` — `_merge_lifespan`
      - 0.2.d `src/a2kit/packages/testing/client.py` — dispatch_startup/shutdown
      - 0.2.e `src/a2kit/packages/di/container.py` — error message ref
      - 0.2.f `tests/test_app_lifecycle_and_di.py`
      - 0.2.g `tests/test_routers.py`
      - 0.2.h `tests/test_in_process_client.py`
      - 0.2.i `tests/test_ambient_ldd_ctx.py`
      - 0.2.j `tests/test_operational_contracts.py`
      - 0.2.k `examples/health_demo/server.py`
      - 0.2.l `examples/resource_pattern/server.py`
- [x] 0.3 FastMCP version pin — confirmed `lifespan(server)` shape works
      with current pin via existing `_merge_lifespan`; adapter retains
      same call shape.

## 1. Library — `a2kit.lifespan.compose` helper

- [x] 1.1 Create `src/a2kit/lifespan.py` exporting
      `compose(*lifespans) -> AsyncContextManager[None]`. Uses
      `AsyncExitStack` via the composed CM body and shields per-leg.
- [x] 1.2 Each leg wrapped in `_ShieldShutdown`: `__aexit__` raises are
      logged via `a2kit.lifecycle` and swallowed; sibling legs unwind.
- [x] 1.3 Re-export from `a2kit.__init__`'s lazy attr table as
      `a2kit.lifespan` (via new `_LAZY_MODULES`).

## 2. Library — `App` lifespan plumbing

- [x] 2.1 `App.__init__` accepts `lifespan=`. Sync `def` rejected at
      construction with `TypeError`.
- [x] 2.2 Signature is fixed at `(app)`. No introspection, no
      auto-resolve.
- [x] 2.3 `App.warm_async_singletons()` iterates async-factory
      singletons and awaits each through `container.aresolve`.
- [x] 2.4 `_startup_handlers`, `_shutdown_handlers`, `on_startup`,
      `on_shutdown`, `has_lifecycle_handlers` removed.
- [x] 2.5 `dispatch_startup` / `dispatch_shutdown` removed (file
      collapsed into `app.py` previously; the functions are now gone
      and replaced by `App.lifespan_cm()`).

## 3. Library — wire lifespan into CLI and MCP transports

- [x] 3.1 `src/a2kit/packages/cli/runtime.py` — `invoke_tool_sync`
      enters `app.lifespan_cm()` around the tool body, once per
      process via `_lifecycle_started` guard.
- [x] 3.2 `src/a2kit/packages/mcp/server.py` — `_build_fastmcp_lifespan`
      wraps `app.lifespan_cm()` in a `lifespan(server)` adapter that
      sets `server._a2kit_app = app` back-reference.
- [x] 3.2.a FastMCP signature confirmed — adapter remains shape-
      compatible with the previous `_merge_lifespan` callable.
- [x] 3.3 `tests/test_singleton_async_factories.py` — async-singleton
      end-to-end test still green via TestClient + lifespan_cm path.

## 3a. Library — Router.lifespan composition (sibling interlock)

- [x] 3a.1 `add_router(r)` records `r.lifespan` if defined; the App's
      `lifespan_cm()` composes user lifespan + router lifespans via
      `a2kit.lifespan.compose`. Order: App-author first, then routers
      in `add_router` order.
- [x] 3a.2 Legacy `_register_router_lifespan` bridge gone; uses the
      compose helper directly.
- [x] 3a.3 Audit verified `_MetaRouter` doesn't define `lifespan`; no
      migration required.

## 4. Library — test client integration

- [x] 4.1 `src/a2kit/packages/testing/client.py` — `__aenter__` calls
      `app.lifespan_cm().__aenter__()`; `__aexit__` calls the matching
      `__aexit__`. Nullcontext-when-empty handled by `lifespan_cm()`.
- [x] 4.2 Override snapshot/restore still ordered: overrides applied
      AFTER lifespan entry (via `client.override(...)`), removed BEFORE
      lifespan exit completes via the same `__aexit__` path.

## 5. Migrate src/ + tests/

- [x] 5.1 `tests/test_singleton_async_factories.py` — already exercises
      `aresolve` directly; no migration needed beyond container error
      message text (5.4 verified).
- [x] 5.2 Every `@on_startup` / `@on_shutdown` test migrated:
      `test_app_lifecycle_and_di.py` rewritten end-to-end against
      lifespan + compose surface; `test_routers.py` uses
      `app.lifespan_cm()`; `test_in_process_client.py` uses
      `lifespan=`; `test_ambient_ldd_ctx.py` uses `lifespan=`;
      `test_operational_contracts.py` uses `lifespan=`.
- [x] 5.3 `grep -rEn "@app\.(on_startup|on_shutdown)" src tests examples`
      returns nothing.

## 6. Migrate examples/

- [x] 6.1 `examples/streaming_logger/server.py` — already uses
      `lifespan` via singletons; no lifecycle hooks in source. Verified
      `import` smoke green.
- [x] 6.2 `examples/tracker/server.py` — same; no lifecycle hooks. Smoke green.
- [x] 6.3 `examples/health_demo/server.py` — migrated to `lifespan=`.
      `examples/resource_pattern/server.py` — migrated to `lifespan=`.
- [x] 6.4 Smoke-tested example imports under the migrated surface.

## 7. Spec edits (deltas in this change's specs/)

- [x] 7.1 `specs/app-lifecycle/spec.md` — already authored for this
      change; no edits needed beyond what shipped in the proposal.
- [x] 7.2 `specs/app-singletons/spec.md` — ditto.
- [x] 7.3 `specs/in-process-test-client/spec.md` — ditto.

## 8. Documentation

- [x] 8.1 `README.md` — current README has no decorator example to
      change; the lifespan example surfaces via the migrated examples
      and CHANGELOG migration recipe.
- [x] 8.2 `CHANGELOG.md` — v0.31.0 entry consolidates all four bundle
      changes (R1+R4+R12, WARN_ONCE, explicit-router-surface, lifespan).
- [x] 8.3 `ANTIPATTERNS.md` — file does not exist; skipped per scope.

## 9. Verification

- [x] 9.1 `make test` + `make lint` green (800 tests; ruff clean).
- [x] 9.2 Cold-start unchanged — cold-start test still passes.
- [x] 9.3 MCP smoke via in-process `_build_fastmcp_lifespan` test in
      `test_app_lifecycle_and_di.py`.
- [ ] 9.4 Tag for release: v0.31.0 — pending user confirmation.
