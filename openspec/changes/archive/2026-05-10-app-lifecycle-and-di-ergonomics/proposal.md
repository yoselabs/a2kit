## Why

a2web (the largest a2kit consumer) carries ~80 LOC of boilerplate that exists solely because a2kit lacks four small primitives: process lifecycle hooks, an App-scoped singleton helper, a synchronous container peek, and a connection-less `resolve` shorthand. The boilerplate is not idle — it includes a multi-pattern lazy-init dance with locks, an `atexit` handler that opens a fresh event loop to close async resources, and a defensive comment defending `lambda: state` over `lru_cache`. These are exactly the patterns a2kit promised to abstract. Closing the gap deletes the patterns from a2web *and* prevents every future a2kit consumer from re-deriving them.

## What Changes

- **NEW**: `App.on_startup(callable)` and `App.on_shutdown(callable)` decorators/methods that register async lifecycle handlers. Handlers run once per `a2kit.run(app)` invocation (CLI path) and once per FastMCP server lifespan (MCP path). Multiple handlers run in registration order on startup and reverse order on shutdown.
- **NEW**: `App.singleton(type_, factory=None)` — registers a typed factory whose result is cached for the lifetime of the *App instance* (not the process, not the request). Distinct from `provide()`, which constructs fresh per-dispatch. Two `App` instances → two singleton instances. Decorator form `@app.singleton(T)` accepted.
- **NEW**: `Container.resolve_sync(type_)` — synchronous resolve for providers whose entire factory chain is sync. Raises `SyncResolveUnavailable` (with a clear message) if any link in the chain is `async`. Primarily for tests and CLI-stub paths that cannot await.
- **MODIFIED**: `Container.resolve(type_, *, connection=None)` — `connection` defaults to `None` (was required positional/keyword). Connection-less apps stop typing dead syntax. No behavior change for connection-using apps.
- **NEW**: `App.has_singleton(type_)` and `App.singletons()` introspection mirrors for tests/diagnostics, paralleling existing `has_provider`/`container().providers()`.
- Failure semantics for lifecycle:
  - Startup handler raises → abort startup, propagate the exception, do NOT run any subsequent startup handlers, do NOT run shutdown handlers (nothing was set up).
  - Shutdown handler raises → log via the App's logger, continue running remaining shutdown handlers, never re-raise.

## Capabilities

### New Capabilities

- `app-lifecycle`: defines `on_startup` / `on_shutdown` registration, ordering, failure semantics, and the contract that both transports (CLI runner and FastMCP server) invoke handlers exactly once per process / per lifespan.
- `app-singletons`: defines `App.singleton(T, factory)`, App-scoped (not process-scoped) caching guarantee, the two-App isolation contract, decorator form, and introspection surface.

### Modified Capabilities

- `request-scoped-di`: `Container.resolve` signature gains a default-`None` `connection` kwarg; new `resolve_sync` requirement is added covering the sync-only resolve path and the `SyncResolveUnavailable` raise condition. `provide()` semantics are unchanged. The "per-call result caching" requirement is unchanged but a clarifying scenario is added: singleton-resolved types short-circuit the request cache and return the App-scoped instance.

## Impact

- **Code added**: ~120 LOC across `src/a2kit/app.py` (lifecycle registry + singleton helpers), `src/a2kit/packages/connections/container.py` (resolve_sync, default-None connection kwarg, singleton bridging), `src/a2kit/runtime.py` and `src/a2kit/packages/mcp/server.py` (CLI/MCP lifespan dispatch).
- **Public API**: additive in App and Container; only `Container.resolve(connection=...)` becomes optional (binary-compatible — old call sites still work).
- **Dependencies**: none.
- **Cold start**: lifecycle registry is a list of callables on App — no new imports on the bare `import a2kit` path.
- **Downstream**: a2web pins `>=` the version that ships this and deletes `_atexit_close`, `ensure_sqlite/proxy_pool/browser_pool`, `register_state`'s closure pattern, the lock fields, and several explanatory comments. Estimated ~70 LOC removed.
- **Tests**: new tests for handler ordering, failure semantics, two-App singleton isolation (the canary that a2web currently maintains becomes redundant), `resolve_sync` happy/error paths, and connection-less resolve.
- **Specs touched**: new `app-lifecycle` and `app-singletons` specs; delta on `request-scoped-di`. No spec deletion.
- **Out of scope**: connection-as-plugin v0.13 work; tool-author guardrail lint rules (separate change `tool-author-guardrails`); LDD event-stream bridge (separate change, gated on `fastmcp-context-passthrough`).
