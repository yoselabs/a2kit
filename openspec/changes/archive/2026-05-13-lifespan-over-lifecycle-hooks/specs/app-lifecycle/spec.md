# app-lifecycle — lifespan-over-lifecycle-hooks delta

## ADDED Requirements

### Requirement: App accepts a `lifespan` async-context-manager argument

The `a2kit.App` class SHALL accept a `lifespan` argument on
construction. The value SHALL be a callable returning an async
context manager (the canonical idiom is a function decorated with
`@contextlib.asynccontextmanager`). The callable's signature SHALL
be exactly one positional parameter, the `a2kit.App` instance
itself. The runtime SHALL NOT introspect the callable for
additional typed parameters and SHALL NOT auto-resolve any
kwargs through the container; users SHALL resolve any startup
dependencies explicitly inside the lifespan body via
`await app.container().aresolve(T)`.

The body of the lifespan runs as: enter context manager → app
serves tool dispatch → exit context manager. Startup work goes
before `yield`; shutdown work goes after `yield` (or inside a
`finally` block).

#### Scenario: Lifespan with App-only signature

- **GIVEN** an `@asynccontextmanager async def lifespan(app)` registered as `App("x", lifespan=lifespan)`
- **WHEN** the runtime enters the lifecycle
- **THEN** the lifespan body runs to `yield`, tool dispatch is permitted, and the body resumes after the unwind exactly once each

#### Scenario: Lifespan resolves singletons explicitly inside body

- **GIVEN** `app.singleton(TrackerStore, build_store_async)` registered and an `@asynccontextmanager async def lifespan(app)` whose body does `store = await app.container().aresolve(TrackerStore)` before `yield`
- **WHEN** the runtime enters the lifecycle
- **THEN** the lifespan body successfully resolves the `TrackerStore` singleton through the container; the runtime did NOT introspect the lifespan signature for typed kwargs and did NOT pre-resolve anything before entering the context manager

#### Scenario: Sync lifespan rejected at construction

- **GIVEN** a `def lifespan(app): ...` defined with `def` rather than `async def` and passed to `App("x", lifespan=lifespan)`
- **WHEN** `App.__init__` runs
- **THEN** `TypeError` is raised naming the lifespan and stating that the callable MUST be defined with `async def` and decorated with `@contextlib.asynccontextmanager`

#### Scenario: Lifespan signature with extra parameters is rejected

- **GIVEN** an `@asynccontextmanager async def lifespan(app, state: AppState)` (extra typed parameter beyond `app`)
- **WHEN** `App("x", lifespan=lifespan)` is constructed and the runtime prepares to enter the lifecycle
- **THEN** the runtime raises a clear error naming the extra parameter and directing the author to resolve dependencies inside the body via `await app.container().aresolve(...)`

### Requirement: Framework adapts a2kit's `lifespan(app)` to FastMCP's `lifespan(server)`

The MCP build path (`build_mcp_server`) SHALL wrap the user's
`async def lifespan(app)` callable in an adapter matching
FastMCP's `lifespan=` slot signature
(`async def lifespan(server: FastMCP[...]) -> AsyncIterator[Any]`).
The adapter SHALL set a back-reference `server._a2kit_app = app`
during build so user code can recover the `a2kit.App` instance
from the FastMCP server when needed. The adapter SHALL enter the
user lifespan via `async with user_lifespan(app):` and yield
inside that block. The CLI runner and test client SHALL call the
user lifespan directly (no adapter needed; they own the App).

#### Scenario: MCP server receives a FastMCP-shaped lifespan

- **GIVEN** an `App("x", lifespan=user_lifespan)` where `user_lifespan` has signature `(app)`
- **WHEN** `build_mcp_server(app)` constructs the FastMCP server
- **THEN** the value passed to FastMCP's `lifespan=` slot is a callable accepting `(server,)`, and entering that adapter (a) sets `server._a2kit_app = app`, and (b) runs `user_lifespan(app)`'s body to `yield`

#### Scenario: User code recovers App from FastMCP server back-reference

- **GIVEN** an MCP-built App where a FastMCP middleware obtains the server instance
- **WHEN** the middleware reads `server._a2kit_app`
- **THEN** it receives the original `a2kit.App` instance

### Requirement: `a2kit.lifespan.compose(*lifespans)` composes multiple lifespans

The library SHALL expose `a2kit.lifespan.compose(*lifespans)` that
returns a single async context manager composing the supplied
lifespans. Startup runs in declared order; shutdown runs in
reverse order (LIFO unwind, via `contextlib.AsyncExitStack`). Each
shutdown leg SHALL be wrapped so that an exception in one leg is
logged via `logging.getLogger("a2kit.lifecycle").error(..., exc_info=True)`
and remaining legs still run.

#### Scenario: Reverse-order unwind in compose

- **GIVEN** `compose(L1, L2, L3)` where each leg records its enter/exit order
- **WHEN** the composed lifespan is entered and exited normally
- **THEN** enter order is L1, L2, L3 and exit order is L3, L2, L1

#### Scenario: Composed lifespan runs App and Router lifespans in declared order

- **GIVEN** an `App("x", lifespan=app_lifespan)` with two routers `r1`, `r2` each defining a `Router.lifespan` async context manager (the `Router.lifespan` surface itself is defined by sibling change `explicit-router-surface`), composed by the framework during `add_router` via `a2kit.lifespan.compose(app_lifespan, r1.lifespan, r2.lifespan)`
- **WHEN** the composed lifespan is entered and exited normally
- **THEN** startup enter order is `app_lifespan`, `r1.lifespan`, `r2.lifespan`, and shutdown exit order is `r2.lifespan`, `r1.lifespan`, `app_lifespan`

#### Scenario: Shutdown failure in one leg does not abort other legs

- **GIVEN** `compose(L1, L2, L3)` where L2's exit raises `RuntimeError("close failed")`
- **WHEN** the composed lifespan exits
- **THEN** L3 ran (entered before L2), L2's exception is logged at ERROR with traceback under logger `a2kit.lifecycle`, L1's exit ran, and the composed lifespan exit returned without raising

### Requirement: Startup failure aborts lifecycle and propagates

If the lifespan body raises before reaching `yield`, the runtime SHALL propagate the exception to the caller of `a2kit.run(app)`, the test client, or `build_mcp_server`, and when `compose(...)` is used, partially entered legs SHALL be unwound by `AsyncExitStack` in reverse order before the exception propagates; any partial setup inside a user-written monolithic lifespan body is the author's responsibility to clean up via `try/finally`.

#### Scenario: Lifespan body raises before yield

- **GIVEN** `@asynccontextmanager async def lifespan(app): raise RuntimeError("boom"); yield`
- **WHEN** `a2kit.run(app, ...)` is called
- **THEN** `RuntimeError("boom")` propagates to the caller and no tool dispatch occurred

#### Scenario: Compose unwinds already-entered legs on mid-stack failure

- **GIVEN** `compose(L1, L2_raises_on_enter, L3)` where L2's enter raises
- **WHEN** the composed lifespan is entered
- **THEN** L1's exit ran (unwound by AsyncExitStack), L3 never entered, and the original exception propagates

## MODIFIED Requirements

### Requirement: Both transports invoke the lifespan exactly once per process / lifespan

The CLI runner (`a2kit.run(app)`) SHALL enter the App's lifespan
once before dispatching the user's subcommand and SHALL exit it
once after the subcommand completes. The MCP server
(`build_mcp_server(app, ...)`) SHALL pass the prepared lifespan
callable to FastMCP's `lifespan=` slot so that startup runs
before any tool is served and shutdown runs after the lifespan
unwinds.

If no `lifespan=` was provided at App construction, the runtime
SHALL behave as if a no-op `nullcontext()` were passed (no
setup, no teardown).

#### Scenario: CLI invocation runs the full lifespan around the subcommand

- **GIVEN** an `App` constructed with a `lifespan=` callable that records enter/exit timestamps
- **WHEN** `a2kit.run(app, ["my-tool", ...])` is called and the tool returns successfully
- **THEN** the lifespan entered before the tool body, exited after the tool body, exactly once each

#### Scenario: MCP server wraps tool dispatch in the lifespan

- **GIVEN** an `App` with a `lifespan=` callable
- **WHEN** `build_mcp_server(app)` is run and a real `fastmcp.Client` connects, dispatches a tool, and disconnects
- **THEN** the lifespan body's pre-yield code ran before the tool dispatch and the post-yield code ran after the client disconnected, exactly once each

#### Scenario: Tool error is preserved when lifespan exit also raises

- **GIVEN** a CLI invocation where the tool body raised `ToolError` and the lifespan exit (within `compose`) subsequently raises `ShutdownError`
- **WHEN** the lifecycle finishes
- **THEN** the caller of `run` sees `ToolError` (not `ShutdownError`)
- **AND** `ShutdownError` was logged under `a2kit.lifecycle` with traceback

## REMOVED Requirements

### Requirement: App exposes `on_startup` and `on_shutdown` registration

**Reason for removal**: `@app.on_startup` and `@app.on_shutdown`
are a bespoke handler-registry re-implementation of FastMCP's
`lifespan=` abstraction. Two registries doing the same job is the
"above-ceiling magic" smell; the framework already provides the
canonical hook. The replacement is a single `lifespan=` async
context manager passed to `App(...)`.

**Migration**:

```python
# Before
@app.on_startup
async def _open(state: AppState):
    await state.open()

@app.on_shutdown
async def _close(state: AppState):
    await state.close()

# After
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app, state: AppState):
    await state.open()
    try:
        yield
    finally:
        await state.close()

app = a2kit.App("name", lifespan=lifespan)
```

For multi-component apps, compose Router-contributed lifespans
via `a2kit.lifespan.compose(...)`.

### Requirement: Lifecycle handlers resolve kwargs via the container

**Reason for removal**: superseded by the new "App accepts a
`lifespan` async-context-manager argument" requirement, which
preserves DI resolution of typed kwargs in a single declarative
shape (the lifespan callable's signature) instead of across a
list of registered handlers.

### Requirement: Shutdown handlers run in reverse registration order

**Reason for removal**: superseded by `a2kit.lifespan.compose`'s
`AsyncExitStack`-driven LIFO unwind. Reverse order remains an
observable property but is now expressed via the new
"Reverse-order unwind in compose" scenario.

### Requirement: Shutdown failure is logged and swallowed; remaining handlers still run

**Reason for removal**: superseded by the new "Shutdown failure
in one leg does not abort other legs" scenario on
`a2kit.lifespan.compose`. The semantic is preserved; the
expression site moved from the dispatcher to the compose helper.

### Requirement: Sync handlers are accepted and run inline

**Reason for removal**: the new shape is built on
`@asynccontextmanager` and requires `async def`. A `def` lifespan
is rejected at `App.__init__` time with `TypeError` (see the
"Sync lifespan rejected at construction" scenario). Sync setup
work goes inside the async body as plain statements — no framework
wrapper, no `asyncio.to_thread` helper.

**Migration**: hand-rewrite sync `@on_startup` / `@on_shutdown`
handler bodies into the async `lifespan` function inline.
