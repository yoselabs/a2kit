## MODIFIED Requirements

### Requirement: Ambient context binding via dispatch contextvar

The library SHALL bind the live transport context (`fastmcp.Context` under MCP, the CLI stub under CLI, the test-client stub under in-process tests) into the per-call `_LddState` carried by `_LDD_STATE: ContextVar[_LddState | None]`. The `ldd_state_for_call(...)` contextmanager SHALL take a required `ctx` keyword argument and store it on the `_LddState` instance set on entry. All LDD primitives SHALL resolve their transport context from `_LDD_STATE.get().ctx` rather than accepting `ctx` as a parameter.

The three dispatch sites SHALL pass `ctx` into `ldd_state_for_call` **only when the tool declared a ctx parameter** (i.e. `meta.context_param_name` is truthy):

- MCP runtime (`_wrap_with_ldd_state` in `a2kit.packages.mcp.server`) installs the wrapper only when `meta.context_param_name` is truthy and passes the `fastmcp.Context` injected by FastMCP.
- CLI runtime (`_invoke_tool_in_process` in `a2kit.packages.cli.runtime`) opens `ldd_state_for_call` only when `ctx_param_name` is truthy and passes the `StderrToolContext` instance bound on the call kwargs. The CLI runtime SHALL NOT synthesize a `StderrToolContext` for tools that did not declare `ctx`.
- In-process test client (`TestClient.invoke` in `a2kit.packages.testing.client`) opens `ldd_state_for_call` only when `meta.context_param_name` is truthy and passes the `_CapturingContext` bound on the call kwargs. The test client SHALL NOT synthesize a capturing context for tools that did not declare `ctx`.

A tool that calls any LDD primitive (`a2kit.ldd.event`, `a2kit.ldd.log`, `a2kit.ldd.info`, etc.) but did NOT declare `ctx: a2kit.ToolContext` SHALL therefore raise `AmbientContextMissing` uniformly across MCP, CLI, and TestClient — there is no transport on which the missing-ctx case silently succeeds.

`contextvars.ContextVar.set` / `.reset` token semantics SHALL be honored — every entry into `ldd_state_for_call` is paired with an exit that resets to the prior state. Nested dispatch (e.g. tool A invokes tool B via the test client) SHALL be supported by the token stack with no additional locking.

#### Scenario: MCP dispatch binds the live fastmcp.Context

- **GIVEN** a tool `async def t(*, ctx: a2kit.ToolContext) -> None: await a2kit.ldd.event("x", k=1)`
- **WHEN** the tool runs under `<app> serve` and FastMCP injects `ctx`
- **THEN** the MCP client receives the `notifications/message` for `"x"` carrying `k=1`
- **AND** the `event` call did not pass `ctx` and did not raise

#### Scenario: CLI dispatch binds the StderrToolContext

- **GIVEN** a tool calling `await a2kit.ldd.info("msg", k=1)` with no `ctx` argument
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** stderr contains a line matching `[ +\d+\.\d+ INFO    ] msg k=1`

#### Scenario: TestClient dispatch binds the test stub

- **GIVEN** a tool calling `await a2kit.ldd.event("x", k=1)` and the in-process `TestClient`
- **WHEN** `await client.call_tool("t", {})` is awaited
- **THEN** the captured emission carries `name="x"` and `k=1` with the test stub as the bound ctx

#### Scenario: Concurrent gather sees the same ambient ctx

- **GIVEN** a tool body that runs `await asyncio.gather(sub_a(), sub_b())` where both sub-coroutines call `a2kit.ldd.event(...)`
- **WHEN** the tool runs under MCP
- **THEN** both emissions resolve to the same ambient `ctx` (the dispatcher's injected `fastmcp.Context`) and neither raises

#### Scenario: Nested dispatch shadows then restores ambient ctx

- **GIVEN** tool A whose body invokes tool B via the in-process test client, where both A and B call `a2kit.ldd.event(...)`
- **WHEN** A runs and B is dispatched mid-way
- **THEN** events emitted from inside B resolve to B's dispatch ctx
- **AND** events emitted from A after B returns resolve again to A's dispatch ctx

#### Scenario: CLI dispatch on a no-ctx tool does not synthesize StderrToolContext

- **GIVEN** a tool `async def t() -> None: await a2kit.ldd.event("x", k=1)` that did NOT declare `ctx`
- **WHEN** the tool runs via `<app> tasks t`
- **THEN** the LDD call raises `AmbientContextMissing` with a message naming `a2kit.ldd.event`
- **AND** the CLI runtime did not synthesize a `StderrToolContext` for the call

#### Scenario: TestClient dispatch on a no-ctx tool does not synthesize a capturing context

- **GIVEN** a tool `async def t() -> None: await a2kit.ldd.event("x", k=1)` that did NOT declare `ctx`
- **WHEN** a test runs `await client.invoke("t")`
- **THEN** the LDD call raises `AmbientContextMissing` with a message naming `a2kit.ldd.event`
- **AND** `client.events` remains empty (no synthesized capturing-context binding)

### Requirement: LDD primitives raise when called outside a dispatch

If any of `a2kit.ldd.event`, `a2kit.ldd.report`, `a2kit.ldd.log`, `a2kit.ldd.debug`, `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, or `EventRegistry.emit_typed` is invoked while `_LDD_STATE.get()` is `None` (i.e. no active `ldd_state_for_call` scope on the current `contextvars.Context`), the call SHALL raise `AmbientContextMissing` (a subclass of `RuntimeError`). The exception message SHALL name the **invoked function** (e.g. `"a2kit.ldd.info"` for `info`, not `"a2kit.ldd.log"`) and SHALL indicate that the primitive must be called from inside a tool body. Shorthand primitives (`debug`, `info`, `warning`, `error`) that delegate internally to `log` SHALL still surface their own name in the message. The library SHALL NOT silently no-op and SHALL NOT synthesize a fallback context.

#### Scenario: Calling event outside a dispatch raises

- **GIVEN** a module-level coroutine that calls `await a2kit.ldd.event("x", k=1)` without first entering `ldd_state_for_call`
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains `"a2kit.ldd.event"` and references the tool-body dispatch contract

#### Scenario: Calling log from a lifecycle hook raises

- **GIVEN** an `on_startup` hook that calls `await a2kit.ldd.info("starting")`
- **WHEN** the app starts up
- **THEN** `AmbientContextMissing` is raised

#### Scenario: emit_typed raises outside a dispatch

- **GIVEN** a coroutine that calls `await app.ldd.events.emit_typed(TierEnded(...))` outside any dispatch
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised

#### Scenario: Shorthand info names itself in the error message

- **GIVEN** a module-level coroutine that calls `await a2kit.ldd.info("x", k=1)` without first entering `ldd_state_for_call`
- **WHEN** the coroutine is awaited
- **THEN** `AmbientContextMissing` is raised
- **AND** the message contains `"a2kit.ldd.info"` (not `"a2kit.ldd.log"`)

#### Scenario: Shorthand warning, error, debug each name themselves

- **WHEN** `await a2kit.ldd.warning("x")`, `await a2kit.ldd.error("x")`, `await a2kit.ldd.debug("x")` are each called outside an active dispatch
- **THEN** each call raises `AmbientContextMissing` whose message names the called shorthand (`"a2kit.ldd.warning"`, `"a2kit.ldd.error"`, `"a2kit.ldd.debug"` respectively), not `"a2kit.ldd.log"`
