# Lifespan over lifecycle hooks

## Why

a2kit currently exposes `@app.on_startup` / `@app.on_shutdown`
decorators and runs them via `dispatch_startup(app)` /
`dispatch_shutdown(app)`. The implementation is a bespoke handler
registry on `src/a2kit/app.py`: two lists (`_startup_handlers`,
`_shutdown_handlers`) and two dispatchers that walk the lists,
resolve typed kwargs through the container, and `await` each entry.

FastMCP already exposes the canonical lifecycle hook for this:
`lifespan=` — an `@asynccontextmanager` passed to the server. It
runs startup work before `yield` and shutdown work after.

Two registries doing the same job is the magic-above-ceiling smell:
the framework reads what the author wrote, but a2kit re-invents the
abstraction the underlying framework already provides. The "find
where this gets wired" question is harder than it needs to be —
half the answer lives in `app.py`'s dispatcher, half in
`build_mcp_server`'s integration with FastMCP's `lifespan`, and the
test-client's `__aenter__` / `__aexit__` walks the dispatcher list a
third time.

Leaning on `lifespan=` collapses the three sites into one, makes the
lifecycle visible at the call site (a context manager you can read
top-to-bottom), and reuses FastMCP's existing composition story.

## What Changes

### Replace the decorator surface with a `lifespan=` argument

- Add `lifespan: Callable[[App], AsyncContextManager[None]] | None = None`
  as an argument on `a2kit.App.__init__`. The callable signature
  is fixed at exactly one positional parameter, the `App`.
- The body of the lifespan runs as: enter context → app is "live"
  → exit context. Tool dispatch happens between enter and exit.
- DI in the lifespan body: explicit, not magic. Users resolve
  singletons inside the body via
  `await app.container().aresolve(SomeResource)`. The framework
  does NOT introspect the lifespan signature for typed kwargs.
  This drops the existing `@on_startup` typed-kwarg convenience
  in favour of an explicit pattern, matching the "no
  attribute-discovery magic" thesis of the paired
  `explicit-router-surface` change.
- FastMCP wiring: a2kit's `lifespan(app)` is wrapped by an
  adapter in `build_mcp_server` to match FastMCP's actual
  `lifespan(server)` slot signature. The framework sets a
  `server._a2kit_app` back-reference during build.
- Remove the `_startup_handlers` / `_shutdown_handlers` lists from
  `App`.
- Remove `@app.on_startup` and `@app.on_shutdown` decorators.
- Remove `dispatch_startup(app)` and `dispatch_shutdown(app)` from
  the public surface.

### Composition for multi-component apps

- `App` accepts a single top-level `lifespan=` callable. Composition
  of multiple component lifespans (e.g. one per Router that opens
  its own resource) is the author's responsibility, expressed as
  nested `async with` blocks inside the top-level lifespan.
- a2kit ships a helper `a2kit.lifespan.compose(*lifespans)` that
  stacks multiple async context managers into one, for the common
  case where each Router wants to contribute startup/shutdown
  without the App author having to write the nesting manually.

### Singleton warm-up integration

- The "warm the async-factory singletons at startup" pattern from
  the `app-singletons` capability moves inside the lifespan body.
  a2kit exposes `await app.warm_async_singletons()` as the
  canonical incantation. Calling it from inside `lifespan` keeps
  the same observable behaviour as the current `@on_startup`
  warm-up handlers.
- The "sync resolve of unresolved async singleton raises" scenario
  in `app-singletons` continues to hold; if the lifespan does not
  call `warm_async_singletons()` and a sync resolve happens later,
  it raises exactly as today.

### Test client integration

- `a2kit.testing.client(app)` enters the App's lifespan on
  `__aenter__` and exits on `__aexit__`. The behaviour is
  observably equivalent to today's `dispatch_startup` /
  `dispatch_shutdown` pair.
- If the App has no lifespan, the test client uses
  `contextlib.nullcontext()` and runs no setup/teardown.

### Hard break, no shim

- Pre-1.0; consumers are the example apps and any user code that
  literally typed `@app.on_startup`. Migration is mechanical:
  ```python
  @asynccontextmanager
  async def lifespan(app):
      # previous @on_startup body
      yield
      # previous @on_shutdown body (LIFO order)
  app = a2kit.App("name", lifespan=lifespan)
  ```
- The change lands as **v0.31.0** breaking minor. CHANGELOG entry
  documents the migration recipe. Users hand-rewrite call sites;
  no codemod, no shim.

### Coordination with `explicit-router-surface`

- This change owns `App.lifespan`. Sibling
  `explicit-router-surface` owns `Router.lifespan` (a per-router
  async context manager method) and removes the legacy
  `Router.on_startup` / `Router.on_shutdown` bridge in
  `add_router` (`src/a2kit/app.py:152-161`).
- The two compose via `a2kit.lifespan.compose(...)` introduced
  by this change. Composition happens inside `add_router` /
  `App.build()` during the sibling's work.
- Both ship paired in v0.31.0. No codemod — users hand-rewrite
  call sites; the rewrites are mechanical.
- Audit confirmed `_MetaRouter` (`health_tool=True` path) does
  NOT use the legacy lifecycle bridge, so no internal-framework
  migration is needed for it.

## Capabilities

### Modified Capabilities

- `app-lifecycle` — full rewrite. The capability moves from
  decorator-registered handlers to a single `lifespan=` async
  context manager. DI resolution of lifespan kwargs is preserved.
  Reverse-order shutdown becomes the natural unwind of nested
  context managers (or `lifespan.compose`'s `ExitStack` behaviour).
  Sync-handler acceptance and "startup failure aborts lifecycle"
  semantics are preserved, expressed through the context manager
  shape.
- `app-singletons` — the async-singleton warm-up requirement now
  references `await app.warm_async_singletons()` called from
  inside the lifespan body, instead of `@on_startup`. The
  "sync resolve of unresolved async singleton raises" requirement
  is unchanged in behaviour; its error message updates to point
  at the lifespan body rather than `@on_startup`.
- `in-process-test-client` — the "lifecycle hooks fire around the
  test session" requirement updates to "the App's lifespan is
  entered on `__aenter__` and exited on `__aexit__`." Public
  behaviour matches today; only the wording and the underlying
  mechanism change.

## Impact

- **Affected code**:
  - `src/a2kit/app.py` — remove `_startup_handlers`,
    `_shutdown_handlers`, `on_startup`, `on_shutdown`. Add
    `lifespan` kwarg on `__init__`. Add
    `warm_async_singletons()` method.
  - `src/a2kit/lifecycle.py` (or wherever `dispatch_startup` /
    `dispatch_shutdown` live) — remove. Add
    `src/a2kit/lifespan.py` with `compose(*lifespans)` helper.
  - `src/a2kit/packages/mcp/server.py` — `build_mcp_server`
    threads `app.lifespan` into FastMCP's `lifespan=` slot
    directly. No more handler-walking integration.
  - `src/a2kit/packages/cli/runner.py` (or wherever the CLI
    runner is) — `a2kit.run(app)` enters / exits the lifespan
    around the dispatched subcommand.
  - `src/a2kit/packages/testing/client.py` — `__aenter__` /
    `__aexit__` enter / exit `app.lifespan`.
  - `tests/test_singleton_async_factories.py` — migrate to call
    `await app.warm_async_singletons()` from a lifespan body.
  - `examples/*/server.py` (every example using `@on_startup` /
    `@on_shutdown`) — migrated to a single `lifespan` callable.

- **APIs**: BREAKING.
  - Every `@app.on_startup` / `@app.on_shutdown` decorator usage
    must be rewritten as a `lifespan` context manager.
  - `dispatch_startup` / `dispatch_shutdown` removed from public
    surface; external test harnesses that called them directly
    must switch to entering the App's lifespan.
  - Migration recipe in CHANGELOG.

- **Dependencies**: none added; `contextlib.asynccontextmanager`
  and `contextlib.AsyncExitStack` are stdlib.

- **Risk**:
  - FastMCP version compatibility — `lifespan=` is in current
    FastMCP releases but the exact signature has shifted across
    versions. Pin or version-gate as needed.
  - Composition semantics differ from the old reverse-order
    LIFO list: `AsyncExitStack` already provides LIFO unwind, so
    the observable behaviour matches as long as the helper uses
    `AsyncExitStack`.
  - "Shutdown handler error is logged and swallowed" — needs
    explicit re-expression as exception handling inside the
    lifespan body or inside `lifespan.compose`'s unwind. Without
    it, an exception during shutdown would propagate from the
    `async with`. The compose helper SHALL wrap each shutdown
    exit in a logger-with-traceback `try/except`.

- **Sibling proposals**:
  - `explicit-router-surface` — coordinated, see above.
  - `align-with-pydantic-and-stdlib` — independent.
  - `rebuild-test-client-on-real-context` — independent. The
    new test client already calls into `dispatch_startup`; once
    this change lands, that integration point becomes
    "enter the App's lifespan" instead. Order does not matter.
