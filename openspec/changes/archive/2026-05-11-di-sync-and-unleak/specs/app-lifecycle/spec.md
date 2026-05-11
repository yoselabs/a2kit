## MODIFIED Requirements

### Requirement: App exposes `on_startup` and `on_shutdown` registration

The `a2kit.App` class SHALL expose `on_startup(handler)` and `on_shutdown(handler)` methods that register process-lifecycle handlers. Each method SHALL accept a callable that takes arbitrary DI-resolvable kwargs (e.g. `state: AppState`) and returns either `None` or an awaitable. Each method SHALL also be usable as a decorator (with or without parens). Multiple handlers MAY be registered for either phase. The methods SHALL return the original handler unchanged so the same call site supports both `app.on_startup(fn)` and `@app.on_startup` decorator usage without divergent return semantics.

#### Scenario: Typed-kwarg method form registers a handler

- **WHEN** `app.on_startup(open_db)` is called with `async def open_db(state: AppState)` defined and `AppState` registered as a singleton
- **THEN** subsequent invocation of the lifecycle resolves `state` via the container and invokes `open_db(state=...)` exactly once before any tool dispatch

#### Scenario: Decorator form with typed kwargs

- **WHEN** a function `async def _close(state: AppState)` is decorated with `@app.on_shutdown`
- **THEN** the function is registered as a shutdown handler and returned unchanged
- **AND** at shutdown the runtime resolves `state` via the container and calls the handler

### Requirement: Lifecycle handlers resolve kwargs via the container

The runtime SHALL resolve each lifecycle handler's kwargs through `container.apply_kwargs(handler, {})` before invocation, matching the model used by `@app.health_check` and tool dispatch. The handler signature determines which singletons / providers are resolved.

#### Scenario: Multiple typed kwargs

- **GIVEN** `async def warmup(state: AppState, settings: AppSettings)` registered as `@on_startup`
- **WHEN** the lifecycle dispatches startup
- **THEN** both `state` and `settings` are resolved through the container and passed to `warmup`

### Requirement: Both transports invoke handlers exactly once per process / lifespan

The CLI runner (`a2kit.run(app)`) SHALL invoke registered startup handlers once before the user's subcommand is dispatched, and registered shutdown handlers once after the subcommand completes. The MCP server (`build_mcp_server(app, ...)`) SHALL incorporate the App's handlers into the FastMCP `lifespan` such that startup handlers run before any tool is served and shutdown handlers run after the lifespan unwinds.

#### Scenario: CLI invocation runs full lifecycle

- **GIVEN** an app with one startup handler (`(state: AppState)`) and one shutdown handler (`(state: AppState)`)
- **WHEN** `a2kit.run(app, ["my-tool", ...])` is called and the tool returns successfully
- **THEN** the startup handler ran exactly once before the tool body with the resolved `state`
- **AND** the shutdown handler ran exactly once after the tool body with the resolved `state`

### Requirement: Shutdown handlers run in reverse registration order

Shutdown handlers SHALL be invoked in the reverse of the order in which they were registered (LIFO), mirroring the unwind order of nested context managers.

#### Scenario: Reverse order on shutdown

- **GIVEN** shutdown handlers S1, S2, S3 registered in that order
- **WHEN** the lifecycle dispatches shutdown
- **THEN** the invocation order is S3, S2, S1

### Requirement: Startup failure aborts lifecycle and propagates

If a startup handler raises an exception, the runtime SHALL NOT invoke any subsequent startup handlers, SHALL NOT invoke any shutdown handlers, and SHALL propagate the original exception. No partial setup is presumed.

#### Scenario: Startup handler raises mid-sequence

- **GIVEN** startup handlers H1 (succeeds), H2 (raises `RuntimeError("boom")`), H3 (would succeed)
- **WHEN** the lifecycle dispatches startup
- **THEN** H1 ran, H2 raised, H3 did not run, no shutdown handler ran

## REMOVED Requirements

### Requirement: Lifecycle handlers receive the `App` instance

**Reason:** Lifecycle handlers were the only registration point in a2kit that bypassed DI. The asymmetry forced consumers to write a `container().resolve(...)` dance in every hook and carry `if container is None` guards. With DI-aware lifecycle handlers, the model is consistent across tools, health checks, lifecycle, and singleton/provider factories.

**Migration:** Hooks that previously took `(app: App)` and called `app.container().resolve(AppState, connection=None)` now take `(state: AppState)` directly. The container resolves the kwarg automatically.
