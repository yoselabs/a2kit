## Why

The tracker example landed in v1.0 with three rough edges that hurt
first-impression DX:

1. **Connection injection requires a stub function.** Authors write
   `async def get_conn(*, connection: str) -> TrackerConn: ...` (a stub
   never called) and then `app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)`.
   Three identifiers — `get_conn` (stub), `get_conn_factory` (helper),
   `as_=get_conn` — for what should be a single fact: "this tool needs
   a TrackerConn." The user wants `Depends(TrackerConn)` to be enough.

2. **Stores are reconstructed in every tool body.** Every tool that
   needs application state writes
   `store = TrackerStore(conn); projects, tasks = store.load_state()`.
   The store has nothing to do with the tool body's logic — it's pure
   wiring repeated N times. Authors should be able to write
   `async def f(*, store: TrackerStore = Depends(TrackerStore))`
   and the runtime composes conn → store automatically.

3. **Router-level enrichers require `staticmethod`.** Today:
   `enricher = staticmethod(tracker_404_enricher)` because Python's
   descriptor protocol turns a plain function attribute into a bound
   method. The `staticmethod` wrapper is mechanical noise. Class kwargs
   via PEP 487 `__init_subclass__` (`class TasksRouter(a2kit.Router, enricher=fn):`)
   reads cleaner.

In addition, the tracker example doesn't yet showcase **listview
adaptability** (default fields / page size / selectable fields / filter)
or **LDD** (`ctx.event` / `ctx.report` / `ctx.info` /
`ctx.report_progress`). Both are v1.0 features that deserve first-class
demonstration in the canonical example.

## What Changes

- **Connection-class as `Depends` key.** `Depends(TrackerConn)` resolves
  through the registered store. Runtime path: `app.connect(TrackerConn)`
  registers the connection class → `Depends(<conn-class>)` in a tool
  signature triggers `store.load(connection_str)` at call time, where
  `connection_str` is read from the tool's `connection: str` kwarg.
  Stub `get_conn` functions and `app.use_factory(get_conn_factory(...), as_=...)`
  no longer required for the common case. Both still work — the new
  path is additive.
- **Store-class as `Depends` key.** `Depends(TrackerStore)` constructs
  `TrackerStore(conn)` automatically. The store class declares its
  connection type via either `TrackerStore.conn_type = TrackerConn` (class
  attribute) OR a generic parameter (`class TrackerStore(Store[TrackerConn])`).
  Runtime resolves conn first via the same path as above, then
  instantiates the store. Stores SHOULD be cheap to construct (no I/O
  in `__init__`); the runtime constructs a fresh store per call.
- **`Router` accepts `enricher` as class kwarg.**
  `class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):`
  captures the enricher at subclass-definition time via
  `__init_subclass__`. The legacy `enricher = staticmethod(fn)` and
  `__init__(enricher=...)` paths still work — the kwarg is additive.
- **Tracker example refresh:**
  - Replace `set_get_conn` / `app.use_factory(...)` plumbing with
    direct `Depends(TrackerConn)` / `Depends(TrackerStore)` usage.
  - Add a `list_view`-decorated tool demonstrating `default_fields`,
    `page_size`, `selectable_fields`, and filter expressions against
    an in-memory list (TasksRouter.list_tasks).
  - Add a tool that uses all four LDD channels: `ctx.event` for
    "import.started" / "import.complete" milestones, `ctx.report` for
    typed batch chunks, `ctx.info` for free-form telemetry, and
    `ctx.report_progress` for numeric progress.
  - Move `tracker_404_enricher` to the class kwarg form.
  - Keep `connection.py` and `store.py` unchanged in shape but wire
    `TrackerStore.conn_type = TrackerConn` (or use Generic[ConnT]) so
    `Depends(TrackerStore)` resolves.
- **Lint update:** add `A2K-DI-CLASS-DEPENDS` (informational, not
  enforcing) — when it sees `Depends(<connection-or-store-class>)`,
  validate the class is registered with `app.connect(...)`. Helps catch
  typos early. Disabled by default; opt-in via lint config.

## Capabilities

### New Capabilities

- `class-based-dependency-injection`: `Depends(<class>)` shortcut for
  registered connection / store classes. Replaces stub-function +
  use_factory pattern for the common case.
- `router-enricher-class-kwarg`: PEP 487 `__init_subclass__` capture
  of the `enricher=` class kwarg.

### Modified Capabilities

- `thin-core-surface`: extends `App.connect(...)` to optionally bind a
  store class; extends `Router` with the `enricher` class kwarg.

## Impact

- **Code:**
  - `src/a2kit/signature.py` — `strip_dependencies` and the resolver
    learn to handle `Depends(<class>)` where the class is a registered
    connection or store. New helpers: `is_connection_class(cls, app)`,
    `is_store_class(cls)`, `resolve_class_dependency(cls, kwargs, app)`.
  - `src/a2kit/app.py` — `App.connect(ConnT, *, store=None)` accepts an
    optional store class. New internal map `_store_classes: dict[type, type]`.
  - `src/a2kit/routers.py` — `Router.__init_subclass__(cls, *, enricher=None, ...)`.
  - `src/a2kit/packages/connections/factory.py` — minor refactor;
    `get_conn_factory` stays for backwards-compat.
  - `src/a2kit/packages/lint/rules/di.py` — new informational rule
    (off by default).
- **Examples:** `examples/tracker/{server.py, deps.py, routers.py, store.py, connection.py, README.md}`
  rewritten to demonstrate the new shape + listview kit + LDD.
- **Tests:** `tests/test_app.py` extends with `app.connect(ConnT, store=...)`
  cases; `tests/test_signature.py` (new) covers `Depends(<class>)`
  resolution; `tests/examples/tracker/` extends with smoke tests for
  the new tools.
- **Docs:** README "API surface" table updates the `App` row;
  CHANGELOG next-version entry; new ANTIPATTERNS entry "don't write
  stub get_conn functions for single-conn apps."
- **Backwards compat:** fully additive. Existing tracker patterns still
  work. The new shape is the recommended path going forward.
- **Cold-start:** unchanged. The new resolution path is a few lines in
  signature.py, no new transitive imports.
