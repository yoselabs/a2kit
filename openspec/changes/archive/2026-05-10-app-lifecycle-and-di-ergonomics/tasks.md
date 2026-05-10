## 1. Container surface — sync resolve & default-None connection

- [x] 1.1 Change `Container.resolve` signature in `src/a2kit/packages/connections/container.py` to `connection: str | None = None` (was required); audit all internal callers.
- [x] 1.2 Add `_is_sync_chain(type_)` helper that walks the provider graph from `type_` and returns the first async factory encountered (or `None` if all sync). Singleton-cached entries short-circuit as sync.
- [x] 1.3 Add `Container.resolve_sync(type_, *, connection=None)` that uses `_is_sync_chain`, raises `SyncResolveUnavailable(type_, async_link=...)` on async links, otherwise resolves synchronously.
- [x] 1.4 Add `SyncResolveUnavailable` exception in `src/a2kit/packages/connections/exceptions.py` (or wherever existing container exceptions live) with `type_` and `async_link` fields and a clear message pointing the user at the async path.
- [x] 1.5 Tests: sync chain resolves; async link raises with named offender; default-None connection on async resolve; default-None on sync resolve; existing `connection="foo"` callers still work. (in `tests/test_app_lifecycle_and_di.py`)

## 2. Singleton primitive

- [x] 2.1 Add `App._singletons: dict[type, Any]` initialized in `App.__init__`.
- [x] 2.2 Add `App.singleton(type_, factory=None)` in `src/a2kit/app.py` supporting both method form (returns `self`) and decorator form (returns the decorator when `factory is None`).
- [x] 2.3 Implement caching wrapper that captures the user's factory, defers to it on first resolve, stores result in `App._singletons[type_]`, and returns the cached value on subsequent resolves. Use a sentinel for "not yet resolved" so `singletons()` can distinguish.
- [x] 2.4 Async-factory path: detect async via `inspect.iscoroutinefunction`; wrap with an `asyncio.Lock` created lazily on the App; coalesce concurrent first-resolves so the factory awaits exactly once.
- [x] 2.5 Connection-dependency rejection: at registration, walk the factory's annotated params; if any resolves to `connection: str` or transitively requires a connection-bound provider, raise `ValueError` naming the offending parameter / chain.
- [x] 2.6 Add `App.has_singleton(type_)` and `App.singletons() -> dict[type, Any]` introspection.
- [x] 2.7 Tests: method-form, decorator-form, single-resolve caching, two-App isolation canary, async-factory single-await with concurrent resolvers, connection-dep rejection (direct + transitive), `has_singleton`/`singletons()` snapshots, `provide`-then-`singleton` last-write-wins. (in `tests/test_app_lifecycle_and_di.py`)

## 3. Lifecycle handlers

- [x] 3.1 Add `App._startup_handlers: list[Callable]` and `App._shutdown_handlers: list[Callable]`.
- [x] 3.2 Add `App.on_startup(fn=None)` and `App.on_shutdown(fn=None)` supporting decorator-with-args and direct-call forms (mirror the pattern used by `singleton`).
- [x] 3.3 Implement `_dispatch_startup(app)` async helper: iterates handlers in registration order; awaits coroutines; calls plain callables inline. On exception, propagates immediately without invoking remaining startup handlers or any shutdown handler.
- [x] 3.4 Implement `_dispatch_shutdown(app)` async helper: iterates handlers in reverse registration order; logs any raised exception via `logging.getLogger("a2kit.lifecycle").exception(...)` and continues; never re-raises.

## 4. CLI wiring

- [x] 4.1 Threaded `app` into `invoke_tool_sync`; lifecycle now runs inside the same `asyncio.run` that wraps the tool body (single event loop for startup → tool → shutdown). Approach is cleaner than wrapping `cli.main`: lifecycle fires only when an actual tool dispatches, not on `--help`/`--version`/`lint`.
- [x] 4.2 Lifecycle dispatch runs in the same async runner as the tool body via `_runner()` in `cli/runtime.py`; no nested-loop issue since the outer `cli.main` is sync Click code dispatching to `invoke_tool_sync` which owns the only `asyncio.run`.
- [x] 4.3 Tests: CLI invocation runs full lifecycle on success; CLI runs shutdown after tool error and exception still propagates; same-loop state isolation; ordering (forward startup, reverse shutdown); shutdown error is logged but not raised. (in `tests/test_app_lifecycle_and_di.py`)

## 5. MCP wiring

- [x] 5.1 Added `_merge_lifespan(app, user_lifespan)` in `mcp/server.py` deriving an `@asynccontextmanager` from `dispatch_startup` / `dispatch_shutdown`.
- [x] 5.2 `build_mcp_server` now sets `fastmcp_kwargs["lifespan"]` to the merged context manager only when handlers are registered; user `lifespan=` is composed inside (a2kit-startup → user-enter → yield → user-exit → a2kit-shutdown).
- [x] 5.3 Tests: MCP lifespan runs handlers in correct order; integrates with user-supplied lifespan; preserves the no-handlers fast path. (in `tests/test_app_lifecycle_and_di.py`)

## 6. Documentation & examples

- [ ] 6.1 Add a "Singletons vs providers" section to `ANTIPATTERNS.md` (or the relevant guide) with the lifetime decision tree. **Deferred** — not blocking the additive release; can land as a follow-up.
- [ ] 6.2 Add `examples/lifecycle/` showing `@app.on_startup` opening a sqlite connection and `@app.singleton(AppState)` caching it. Mirrored CLI + MCP example. **Deferred** — see CHANGELOG migration snippet for the canonical pattern.
- [x] 6.3 Update `CHANGELOG.md` with the new public API (`on_startup`, `on_shutdown`, `singleton`, `resolve_sync`, default-`None` `connection`) and migration notes (additive — no breakage).

## 7. Verification

- [x] 7.1 Run full test suite — 532 passed (was 503; added 29 new tests in `tests/test_app_lifecycle_and_di.py`).
- [x] 7.2 Run lint — `make lint` clean (ruff check, ruff format, ty type-check, a2kit static lint all green).
- [x] 7.3 Validate openspec change — `openspec validate app-lifecycle-and-di-ergonomics --strict` passes.
- [x] 7.4 Cold-start invariant smoke — `import a2kit` does not pull `fastmcp`; verified via `sys.modules` inspection.
- [ ] 7.5 Manual a2web integration check. **Deferred to a2web's PR** — that work is owned by the consumer once they pin the new a2kit version. CHANGELOG migration snippet documents the pattern.
