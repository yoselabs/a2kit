# Tasks — lifespan over lifecycle hooks

## 0. Prerequisites

- [ ] 0.1 Baseline: `make test` + `make lint` green.
- [ ] 0.2 Inventory every `@on_startup` / `@on_shutdown` call site
      across `src/`, `tests/`, and `examples/` — record paths in
      this task file as 0.2.a, 0.2.b, … so nothing is missed.
- [ ] 0.3 Confirm FastMCP version pin supports the target
      `lifespan=` signature; bump minimum if needed.

## 1. Library — `a2kit.lifespan.compose` helper

- [ ] 1.1 Create `src/a2kit/lifespan.py` exporting
      `compose(*lifespans) -> AsyncContextManager[None]` per
      design D-COMPOSE. Uses `contextlib.AsyncExitStack`.
- [ ] 1.2 Wrap each `__aexit__` leg in `try/except` that logs
      via `logging.getLogger("a2kit.lifecycle").error(..., exc_info=True)`
      and continues unwinding (preserves
      "Shutdown failure logged and swallowed" semantics).
- [ ] 1.3 Re-export from `a2kit.__init__`'s lazy attr table as
      `a2kit.lifespan`.

## 2. Library — `App` lifespan plumbing

- [ ] 2.1 Add `lifespan: Callable[..., AsyncContextManager[None]] | None = None`
      to `a2kit.App.__init__`. Reject a non-async (`def`) lifespan
      at construction time with `TypeError` per D-HARD-BREAK and
      the "Sync lifespan rejected at construction" scenario in
      the `app-lifecycle` spec delta.
- [ ] 2.2 Fix the lifespan signature at `(app: a2kit.App)`
      exactly. Do NOT introspect for typed kwargs and do NOT
      auto-resolve through the container (D-DI-IN-LIFESPAN).
      Users resolve singletons explicitly via
      `await app.container().aresolve(T)` inside the body.
- [ ] 2.3 Add `await app.warm_async_singletons()` method that
      iterates `app.singletons()` and awaits each async-factory
      entry through the container (D-WARM-SINGLETONS).
- [ ] 2.4 Remove `_startup_handlers`, `_shutdown_handlers`, and
      `on_startup` / `on_shutdown` methods from `App`.
- [ ] 2.5 Remove `dispatch_startup(app)` and
      `dispatch_shutdown(app)` from `src/a2kit/lifecycle.py` (or
      wherever they live). Delete the file if it becomes empty.

## 3. Library — wire lifespan into CLI and MCP transports

- [ ] 3.1 `src/a2kit/packages/cli/runner.py` (or equivalent):
      `a2kit.run(app)` enters `app.lifespan(app, **resolved)`
      before dispatching the subcommand and exits it after.
- [ ] 3.2 `src/a2kit/packages/mcp/server.py`: `build_mcp_server`
      wraps the user's `lifespan(app)` callable in a FastMCP
      adapter that matches FastMCP's `lifespan(server)`
      signature (D-FASTMCP-ADAPTER). The adapter sets
      `server._a2kit_app = app` as a back-reference and calls
      `async with user_lifespan(app): yield` inside the
      FastMCP-shaped context manager.
- [ ] 3.2.a Confirm the FastMCP `lifespan=` signature against
      the pinned FastMCP version (current target:
      `async def lifespan(server: FastMCP[...]) -> AsyncIterator[Any]`,
      per `fastmcp/server/server.py:237`). Update the adapter
      if the upstream signature shifts.
- [ ] 3.3 Confirm async-singleton warm-up triggered from inside
      the lifespan body works on both transports (existing
      regression tests in `tests/test_singleton_async_factories.py`
      green after migration).

## 3a. Library — Router.lifespan composition (sibling interlock)

- [ ] 3a.1 Verify `add_router(r)` composes `r.lifespan` (if the
      sibling `explicit-router-surface` has defined it) into the
      App's lifespan during `App.build()` via
      `a2kit.lifespan.compose(...)`. Composition order: App-author
      lifespan first, then each Router's lifespan in
      `add_router`-call order (startup); reverse on shutdown.
- [ ] 3a.2 Confirm the legacy `add_router` bridge at
      `src/a2kit/app.py:152-161` (auto-registering Router
      `on_startup` / `on_shutdown` methods on the App) is removed
      together with the App-side decorators. Coordinate with
      sibling — the bridge MUST be gone before v0.31.0 ships.
- [ ] 3a.3 Audit confirmed `_MetaRouter` (`health_tool=True`
      path, `src/a2kit/app.py:109-117`) does NOT use the legacy
      lifecycle hooks; no internal migration task needed for it
      (see design D-HEALTH-TOOL-AUDIT).

## 4. Library — test client integration

- [ ] 4.1 `src/a2kit/packages/testing/client.py`: `__aenter__`
      enters `app.lifespan(app)` (or `nullcontext()` if
      `app.lifespan is None`); `__aexit__` exits it. No
      kwarg resolution — signature is fixed at `(app,)` per
      D-DI-IN-LIFESPAN.
- [ ] 4.2 Confirm `TestClient.override` semantics interact
      correctly with the lifespan (overrides applied AFTER
      lifespan entry, removed BEFORE lifespan exit).

## 5. Migrate src/ + tests/

- [ ] 5.1 Migrate `tests/test_singleton_async_factories.py` to
      use a lifespan body that calls
      `await app.warm_async_singletons()`.
- [ ] 5.2 Migrate every `@on_startup` / `@on_shutdown` call site
      identified in 0.2 to a lifespan callable.
- [ ] 5.3 Search-and-confirm zero remaining decorator usages:
      `grep -rEn "@app\.(on_startup|on_shutdown)" src tests examples`
      returns nothing.

## 6. Migrate examples/

- [ ] 6.1 `examples/streaming_logger/server.py` — single
      lifespan callable.
- [ ] 6.2 `examples/tracker/server.py` — single lifespan
      callable.
- [ ] 6.3 Any other example using lifecycle hooks — same.
- [ ] 6.4 `make examples` green.

## 7. Spec edits (deltas in this change's specs/)

- [ ] 7.1 `specs/app-lifecycle/spec.md` — full rewrite per
      proposal. Decorator requirements REMOVED; lifespan
      requirements ADDED.
- [ ] 7.2 `specs/app-singletons/spec.md` — update sync-resolve
      error-message scenario to reference the lifespan body; add
      ADDED requirement for `warm_async_singletons()`.
- [ ] 7.3 `specs/in-process-test-client/spec.md` — update
      "lifecycle hooks fire around the test session" scenario to
      "App's lifespan is entered on `__aenter__` and exited on
      `__aexit__`."

## 8. Documentation

- [ ] 8.1 `README.md` lifecycle section: replace decorator
      example with a lifespan example. Show `lifespan.compose`.
- [ ] 8.2 `CHANGELOG.md`: BREAKING entry under v0.31.0 with the
      migration recipe from design D-HARD-BREAK.
- [ ] 8.3 `ANTIPATTERNS.md` (if it exists): new entry
      "Re-implementing FastMCP's `lifespan=` as a handler
      registry."

## 9. Verification

- [ ] 9.1 `make test` + `make lint` green.
- [ ] 9.2 Cold-start unchanged: `time a2kit --help` matches
      v0.27.2 baseline within noise.
- [ ] 9.3 MCP smoke test against a real `fastmcp.Client`: startup
      and shutdown both observed in lifespan body.
- [ ] 9.4 Tag for release: v0.31.0.
