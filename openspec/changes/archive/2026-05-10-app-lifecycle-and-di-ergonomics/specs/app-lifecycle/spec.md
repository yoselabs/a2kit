## ADDED Requirements

### Requirement: App exposes `on_startup` and `on_shutdown` registration

The `a2kit.App` class SHALL expose `on_startup(handler)` and `on_shutdown(handler)` methods that register process-lifecycle handlers. Each method SHALL accept a callable that takes one argument (the `App`) and returns either `None` or an awaitable. Each method SHALL also be usable as a decorator (with or without parens). Multiple handlers MAY be registered for either phase. The methods SHALL return the original handler unchanged so the same call site supports both `app.on_startup(fn)` and `@app.on_startup` decorator usage without divergent return semantics.

#### Scenario: Method form registers a handler

- **WHEN** `app.on_startup(open_db)` is called with `async def open_db(a)` defined
- **THEN** subsequent invocation of the lifecycle by either transport invokes `open_db(app)` exactly once before any tool dispatch
- **AND** the call returns `open_db` unchanged (so it remains directly callable for tests)

#### Scenario: Decorator form registers a handler

- **WHEN** a function is decorated with `@app.on_shutdown`
- **THEN** the function is registered as a shutdown handler and returned unchanged so it remains callable directly

#### Scenario: Multiple handlers registered

- **WHEN** three handlers are registered for `on_startup` in registration order H1, H2, H3
- **THEN** lifecycle dispatch invokes them in the order H1, H2, H3

### Requirement: Both transports invoke handlers exactly once per process / lifespan

The CLI runner (`a2kit.run(app)`) SHALL invoke registered startup handlers once before the user's subcommand is dispatched, and registered shutdown handlers once after the subcommand completes (whether by success or by exception). The MCP server (`build_mcp_server(app, ...)`) SHALL incorporate the App's handlers into the FastMCP `lifespan` such that startup handlers run before any tool is served and shutdown handlers run after the lifespan unwinds.

#### Scenario: CLI invocation runs full lifecycle

- **GIVEN** an app with one startup handler and one shutdown handler
- **WHEN** `a2kit.run(app, ["my-tool", ...])` is called and the tool returns successfully
- **THEN** the startup handler ran exactly once before the tool body
- **AND** the shutdown handler ran exactly once after the tool body

#### Scenario: CLI invocation runs shutdown on tool error

- **GIVEN** an app with a startup and a shutdown handler
- **WHEN** `a2kit.run(app, [...])` is called and the tool body raises
- **THEN** the shutdown handler ran exactly once after the tool body raised
- **AND** the original tool exception is propagated to the caller of `run`

#### Scenario: MCP lifespan integrates handlers

- **GIVEN** an app with startup and shutdown handlers
- **WHEN** `build_mcp_server(app)` is called and the resulting FastMCP server starts and stops
- **THEN** all startup handlers ran before the server accepted any tool call
- **AND** all shutdown handlers ran after the server stopped accepting calls

#### Scenario: User-supplied MCP lifespan composes with App handlers

- **GIVEN** an app with startup handlers H1, H2 and shutdown handlers S1, S2 (registered in that order)
- **AND** the user calls `build_mcp_server(app, lifespan=user_cm)` where `user_cm` is an async context manager wrapping body B
- **WHEN** the server lifecycle runs
- **THEN** the order is: H1 → H2 → user_cm.__aenter__ → B → user_cm.__aexit__ → S2 → S1

### Requirement: Shutdown handlers run in reverse registration order

Shutdown handlers SHALL be invoked in the reverse of the order in which they were registered (LIFO), mirroring the unwind order of nested context managers.

#### Scenario: Reverse order on shutdown

- **GIVEN** shutdown handlers S1, S2, S3 registered in that order
- **WHEN** the lifecycle dispatches shutdown
- **THEN** the invocation order is S3, S2, S1

### Requirement: Startup failure aborts lifecycle and propagates

If a startup handler raises an exception, the runtime SHALL NOT invoke any subsequent startup handlers, SHALL NOT invoke any shutdown handlers, and SHALL propagate the original exception to the caller of `run` (CLI) or to FastMCP (MCP). No partial setup is presumed.

#### Scenario: Startup handler raises mid-sequence

- **GIVEN** startup handlers H1 (succeeds), H2 (raises `RuntimeError("boom")`), H3 (would succeed)
- **WHEN** the lifecycle dispatches startup
- **THEN** H1 ran, H2 raised, H3 did not run, no shutdown handler ran
- **AND** `RuntimeError("boom")` is raised to the caller

### Requirement: Shutdown failure is logged and swallowed; remaining handlers still run

If a shutdown handler raises, the runtime SHALL log the exception (logger name `a2kit.lifecycle`, level ERROR, with traceback), SHALL invoke remaining shutdown handlers, and SHALL NOT re-raise. The original exit reason (if any) SHALL NOT be masked.

#### Scenario: One shutdown handler raises, others run

- **GIVEN** shutdown handlers S1, S2 (raises `RuntimeError("close failed")`), S3, registered in that order
- **WHEN** the lifecycle dispatches shutdown (LIFO: S3 first)
- **THEN** S3 ran, S2 raised and was logged, S1 ran
- **AND** the lifecycle dispatch completed without raising

#### Scenario: Tool error is preserved when shutdown also raises

- **GIVEN** a CLI invocation where the tool body raised `ToolError` and a shutdown handler subsequently raises `ShutdownError`
- **WHEN** the lifecycle finishes
- **THEN** the caller of `run` sees `ToolError` (not `ShutdownError`)
- **AND** `ShutdownError` was logged

### Requirement: Sync handlers are accepted and run inline

`on_startup` and `on_shutdown` SHALL accept plain (non-async) callables. The runtime SHALL invoke them inline (not in a thread) during the async lifecycle dispatch.

#### Scenario: Sync handler accepted

- **WHEN** `app.on_startup(lambda a: setattr(a, "_marker", True))` is registered
- **THEN** during startup the lambda is called and `app._marker is True` afterward
