# Design — lifespan over lifecycle hooks

## Context

Today the App carries two parallel handler registries
(`_startup_handlers`, `_shutdown_handlers`) plus `dispatch_startup` /
`dispatch_shutdown` runners. FastMCP exposes the canonical
abstraction (`lifespan=`) for the same job. This change collapses
a2kit's bespoke registry into FastMCP's.

## Decisions

### D-LIFESPAN-SHAPE — lifespan is a single async context manager

Public shape:

```python
from contextlib import asynccontextmanager
import a2kit

@asynccontextmanager
async def lifespan(app: a2kit.App):
    await app.warm_async_singletons()
    store = await app.container().aresolve(TrackerStore)
    try:
        yield
    finally:
        await store.close()

app = a2kit.App("tracker", lifespan=lifespan)
```

The lifespan is one function, not a registry of handlers. Readers
see the whole startup / shutdown story in one place, top-to-bottom.
The callable's signature is fixed: exactly one positional parameter,
the `a2kit.App` instance itself. No reflection-based kwarg
injection (see D-DI-IN-LIFESPAN).

### D-FASTMCP-ADAPTER — a2kit's `lifespan(app)` adapts to FastMCP's `lifespan(server)`

FastMCP's `lifespan=` slot expects a callable with signature
`async def lifespan(server: FastMCP[...]) -> AsyncIterator[Any]` —
it passes the **server**, not the App. (See
`fastmcp/server/server.py:237`, `default_lifespan(server: FastMCP[LifespanResultT])`.)

a2kit's user-facing surface is `async def lifespan(app: a2kit.App)`.
The framework adapts shapes inside `build_mcp_server`:

```python
# src/a2kit/packages/mcp/server.py (build path)
def _wrap_for_fastmcp(user_lifespan, a2kit_app):
    @asynccontextmanager
    async def _fastmcp_adapter(server):
        # back-reference set during build so user code can recover
        # the App from the FastMCP server if it ever needs to.
        server._a2kit_app = a2kit_app  # noqa: SLF001 — framework wiring
        async with user_lifespan(a2kit_app):
            yield
    return _fastmcp_adapter
```

Rationale:

- (a) Users see `lifespan(app: App)` — the natural a2kit shape;
  no FastMCP type leaks into their code.
- (b) The framework adapts to FastMCP's `lifespan(server)` shape
  in the MCP build path.
- (c) The App is recoverable from the FastMCP server via the
  `server._a2kit_app` back-reference set during build, for
  power users who need it.

The CLI runner and test client do not need the adapter — they
call `user_lifespan(app)` directly because they own the App
themselves.

### D-DI-IN-LIFESPAN — no DI-kwargs in lifespan signature; resolve explicitly

The lifespan callable's signature is exactly:

```python
async def lifespan(app: a2kit.App) -> AsyncIterator[None]
```

a2kit does NOT introspect the lifespan signature for typed
kwargs and does NOT auto-resolve them through the container.
Users who need a singleton at startup resolve it explicitly
inside the lifespan body:

```python
@asynccontextmanager
async def lifespan(app: a2kit.App):
    store = await app.container().aresolve(TrackerStore)
    try:
        yield
    finally:
        await store.close()
```

Rationale: explicit beats magic. This proposal pairs with
`explicit-router-surface`, whose entire thesis is "no
attribute-discovery magic." Adding signature-reflection here
would re-introduce the same smell on a different surface. The
existing `@on_startup` DI-kwargs trick was convenient but
made "where does `store` come from?" answerable only by
reading the framework. The explicit pattern is two extra lines
and zero magic.

Migration impact: existing `@on_startup` handlers that declared
typed kwargs become explicit `aresolve` calls inside the
lifespan body. Users migrate by hand; the rewrite is mechanical.

### D-COMPOSE — composition via `a2kit.lifespan.compose(*lifespans)`

Multi-component apps (App + several Routers each opening a
resource) compose their lifespans via:

```python
app_lifespan = a2kit.lifespan.compose(
    routers_a.lifespan,
    routers_b.lifespan,
    custom_app_lifespan,
)
app = a2kit.App("x", lifespan=app_lifespan)
```

`compose` is built on `contextlib.AsyncExitStack`. Startup runs in
declared order; shutdown runs in reverse order (the natural
unwind), matching the existing `app-lifecycle` LIFO scenario.

Each `__aexit__` is wrapped in `try/except` that logs the
exception via `logger = logging.getLogger("a2kit.lifecycle")` at
ERROR with traceback and continues unwinding. This preserves the
"shutdown failure logged and swallowed" requirement from
`app-lifecycle`.

### D-WARM-SINGLETONS — explicit `warm_async_singletons()`

The async-singleton warm-up is no longer implicit; the author
calls `await app.warm_async_singletons()` from inside the
lifespan body. The method iterates `app.singletons()`, awaits
each async-factory entry through the container (per-type lock
already provided by `app-singletons` capability), and returns
once every async singleton is resolved.

If the lifespan does not call it, the existing
"sync resolve of unresolved async singleton raises" requirement
fires at first sync resolve, with the error message updated to
point at the lifespan body as the recommended warm-up site.

### D-TEST-CLIENT — TestClient wraps the lifespan as one async-with

The test client's `__aenter__` does:

```python
self._lifespan_cm = app.lifespan(app) if app.lifespan else nullcontext()
await self._lifespan_cm.__aenter__()
```

and `__aexit__` does the matching exit. Observable behaviour
matches the current "startup runs before first invoke; shutdown
runs after the block exits, exactly once each" scenario.

### D-HARD-BREAK — no shim period

Decorator path is removed in v0.31.0. The migration is a
two-minute rewrite per call site:

```python
# Before
@app.on_startup
async def _open(state: AppState): ...
@app.on_shutdown
async def _close(state: AppState): ...

# After
@asynccontextmanager
async def lifespan(app, state: AppState):
    await _open(state)
    try:
        yield
    finally:
        await _close(state)
app = a2kit.App("x", lifespan=lifespan)
```

No shim because pre-1.0 + small consumer surface + the shim's
complexity (registering `@on_startup` calls as injected lifespan
fragments) exceeds the migration cost.

### D-EXCEPTIONS — startup failure / shutdown failure semantics

- Startup failure: an exception inside the lifespan body before
  `yield` propagates to the caller of `a2kit.run(app)` or to the
  test client. Any partial state inside the lifespan body is the
  author's to clean up (they own the `try`/`finally`). This
  preserves the `app-lifecycle` "Startup failure aborts lifecycle
  and propagates" requirement.
- Shutdown failure: the per-leg `try/except` in `compose` logs
  and swallows so subsequent unwinds still run. A user-written
  monolithic lifespan that does not catch exceptions on shutdown
  WILL propagate them; this is a deliberate consequence of
  "leave it to the user when they wrote one lifespan; help them
  when they used `compose`". The migration documentation makes
  this distinction explicit.

### D-ROUTER-COMPOSITION — Router.lifespan owned by sibling proposal

This change owns `App.lifespan`. Sibling `explicit-router-surface`
owns `Router.lifespan` (per-router async context manager method,
replacing the legacy `Router.on_startup` / `Router.on_shutdown`
methods that `App.add_router` currently auto-registers at
`src/a2kit/app.py:152-161`).

The two compose via `a2kit.lifespan.compose(...)` introduced by
this change. Both ship paired in **v0.31.0**.

Integration contract (this change provides; sibling consumes):

- `a2kit.lifespan.compose(*lifespans)` is the canonical
  composition primitive. Sibling's `add_router` calls into it
  when stitching Router lifespans onto the App's lifespan during
  `App.build()` (or equivalent), so the App-author-supplied
  `lifespan=` and each Router's `lifespan` run in declared order
  on startup, reverse order on shutdown.
- The spec scenario "Composed lifespan runs App + Router
  lifespans in declared order" lives in this change's
  `app-lifecycle` delta. The Router-side definition of
  `Router.lifespan` lives in the sibling — not redefined here.

If the sibling lands first, `add_router`'s legacy
`on_startup`/`on_shutdown` bridge keeps working until this
change removes the App-side decorators. If this change lands
first, the legacy bridge becomes a dead branch (since the
decorators no longer exist) and the sibling cleans it up.
Either order works; both must ship in v0.31.0.

### D-HEALTH-TOOL-AUDIT — `_MetaRouter` does NOT use legacy lifecycle

Audit result for `health_tool=True` path
(`grep on_startup|on_shutdown|_MetaRouter|HealthRegistry
src/a2kit/packages/health/ src/a2kit/app.py`):

- `_MetaRouter` (`src/a2kit/app.py:109-117`) only registers a
  single `@_read` tool (`aggregated_health`). It does NOT
  declare `on_startup` or `on_shutdown`.
- `HealthRegistry` is wired at `App.__init__`
  (`src/a2kit/app.py:75-77`). Its lifecycle is App construction,
  not lifecycle hooks.
- The aggregator runs DI resolution at call time via
  `app._container.apply_kwargs(...)`
  (`src/a2kit/packages/health/__init__.py:103`), not via
  lifecycle handlers.

Consequence: the `health_tool=True` path does NOT need
migration as part of this change. No internal-framework
follow-up task required for `_MetaRouter`.

The only `on_startup` / `on_shutdown` consumer left in
framework code is the `add_router` bridge at
`src/a2kit/app.py:152-161`, which is owned by sibling
`explicit-router-surface`.

## Open questions resolved

### Q1 — DI in lifespan: NO. Resolve explicitly via `await app.container().aresolve(...)`

Resolved at D-DI-IN-LIFESPAN. The lifespan signature is fixed at
`(app: a2kit.App)`. No signature reflection, no auto-injected
kwargs. Users resolve singletons explicitly inside the body.

### Q2 — Composition: ship `a2kit.lifespan.compose(*lifespans)`

Resolved at D-COMPOSE. Backed by `AsyncExitStack`.

### Q3 — Test client compatibility: enter the lifespan as one async-with

Resolved at D-TEST-CLIENT. The legacy
`dispatch_startup`/`dispatch_shutdown` pair is gone.

### Q4 — Migration path: hard break in v0.31.0

Resolved at D-HARD-BREAK. CHANGELOG carries the recipe.

## Risks

- **FastMCP version compatibility.** `lifespan=` signature has
  shifted across FastMCP versions. Pin the minimum version that
  supports the current shape (or vendor a thin adapter).
- **AsyncExitStack semantics edge cases.** If a startup leg
  raises mid-stack, `AsyncExitStack` unwinds already-entered
  legs. This matches the existing "startup failure aborts
  lifecycle" requirement (partial setup IS unwound, contrary to
  today's text which says no shutdown handler ran). The spec
  delta SHALL clarify this difference: today partial-startup
  state is leaked; the new shape cleans it up properly.
  Behaviour is strictly better.
- **Sync lifespan rejected at construction.** The lifespan
  callable MUST be defined with `async def`. A plain `def`
  lifespan raises `TypeError` at `App.__init__` time. Sync
  setup work goes inside the async body as plain statements;
  the framework provides no sync wrapper.

## Migration plan

Users hand-rewrite call sites. The mechanical rewrite per call
site: union the `@on_startup` bodies (in registration order)
before `yield` in an `@asynccontextmanager async def lifespan(app):`
function; union the `@on_shutdown` bodies (in reverse order) after
`yield` inside a `finally:` block; replace typed-kwarg handler
params with explicit `await app.container().aresolve(T)` calls;
pass `lifespan=lifespan` to `a2kit.App(...)`. Multiple App-level
lifespans in one module compose via `a2kit.lifespan.compose(...)`.
No codemod, no shim. CHANGELOG and README carry the recipe.
