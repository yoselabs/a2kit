# in-process-test-client Specification

## MODIFIED Requirements

### Requirement: In-process test client

The system SHALL provide `a2kit.testing.client(app)` — an async context manager that runs the **real FastMCP in-memory transport** in-process and exposes capture surfaces for assertions. The test client SHALL build a `FastMCP` server via `build_mcp_server(app)` and connect to it through `fastmcp.Client(transport=server, ...)`, exercising the same dispatch path production MCP transport uses.

The test client SHALL NOT subclass `StderrToolContext` or otherwise construct a CLI-shaped fake of the runtime Context.

App lifecycle around the test session SHALL follow the `app-lifecycle` capability: the App's `__aenter__` runs before the first invoke and its `__aexit__` runs after the block exits. Startup and shutdown bookends are expressed as DI-managed resources registered with `app.provide(T, factory)`; their `__aenter__` / `__aexit__` are entered and unwound by the framework around the App lifecycle. Lifecycle is the async-context-manager protocol plus lazy first-use resource entry.

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
- **AND** DI-managed resources registered via `app.provide(T, factory)` had their `__aenter__` / `__aexit__` entered and unwound around the session
