## MODIFIED Requirements

### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async context manager that runs the **real FastMCP in-memory transport** in-process and exposes capture surfaces for assertions. The test client SHALL build a `FastMCP` server via `build_mcp_server(app)` and connect to it through `fastmcp.Client(transport=server, ...)`, exercising the same dispatch path production MCP transport uses.

The test client SHALL NOT subclass `StderrToolContext` or otherwise construct a CLI-shaped fake of the runtime Context.

App lifecycle around the test session SHALL follow the `app-lifecycle` capability: the App's `__aenter__` runs before the first invoke and its `__aexit__` runs after the block exits. The framework does not expose `@app.on_startup` / `@app.on_shutdown` decorators (they do not exist on `App`); lifecycle is the async-context-manager protocol plus lazy first-use resource entry.

#### Scenario: ctx received by tools is a real fastmcp.Context

- **WHEN** a tool's body runs under `async with a2kit.testing.client(app)`
- **THEN** the ctx argument satisfies `isinstance(ctx, fastmcp.Context)`
- **AND** `isinstance(ctx, StderrToolContext)` is False

#### Scenario: invoke runs the same code path as production dispatch

- **WHEN** a test calls `await client.invoke("tasks.create", name="x")` on an app with `TasksRouter`
- **THEN** the dispatcher resolves DI, runs decorator processing, executes the tool body, and returns the value the tool returned, with the dispatch routed through the real FastMCP server

#### Scenario: App lifecycle fires around the test session

- **WHEN** a test enters `async with a2kit.testing.client(app) as c:` and exits the block
- **THEN** the App's `__aenter__` ran before the first invoke and its `__aexit__` ran after the block exited, each exactly once
- **AND** no `@app.on_startup` / `@app.on_shutdown` decorator is required or available

### Requirement: Hidden `_meta.*` tools invocable in tests

The test client SHALL re-enable the `_meta` tag on the server it builds so hidden protocol-meta tools (e.g. `_meta.health`) are invocable via `invoke()`. Production MCP transport hides them via `server.disable(tags={"_meta"})`; the test client opts back in so test authors can probe health and other meta surfaces. The `_meta.health` tool exists only on Apps that have at least one `@app.health_check` registration — the framework does not accept an `App(health_tool=True)` constructor keyword (it does not exist).

#### Scenario: _meta.health invocable through test client

- **GIVEN** an `App("a")` with at least one `@app.health_check`-registered function
- **WHEN** the test calls `await client.invoke("_meta.health")`
- **THEN** the call succeeds and the result includes the aggregated health payload

## REMOVED Requirements

### Requirement: TestClient.override swaps DI-resolved dependencies for the session

**Reason**: `TestClient.override(...)` does not exist; it was removed in v0.40. The requirement also delegated to `Container._override` / `_snapshot` / `_restore`, none of which exist (see `di-container-package`). The post-seal override seam was deleted: test-time dependency swaps are done by composition-root re-registration, not by mutating a sealed container. The requirement additionally referenced `app.singleton(...)` (renamed to `app.provide`) and a per-session restore mechanism that has no backing code.

**Migration**: To swap a dependency for a fake in tests, construct a fresh `App`, call `app.provide(T, fake)` (last-write-wins re-registration), and hand that `App` to `a2kit.testing.client`. There is no `c.override(...)` call and no restore step — each test builds its own `App`. See the `request-scoped-di` capability's "Re-registration is last-write-wins (test override pattern)" scenario.
