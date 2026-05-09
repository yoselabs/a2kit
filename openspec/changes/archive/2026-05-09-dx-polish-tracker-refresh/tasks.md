## 0. Prerequisites

- [x] 0.1 Confirm `v1-cleanup-debt` and `ldd-streaming-reports` are applied (both already on `v1-thin-core` branch).
- [x] 0.2 Capture baseline: `make lint` exits 0; `make test` → 484 passed; coverage ≥ 94%; cold-start budgets met.

## 1. Core — `a2kit.Store` marker + class-attribute path

- [x] 1.1 Create `src/a2kit/store.py` with a small `Store(Generic[ConnT])` marker class. Goal: ≤ 30 LOC. No methods, no init logic — purely a type anchor for `Generic[ConnT]` introspection.
- [x] 1.2 Lazy-export `Store` from `a2kit/__init__.py` via `_LAZY_ATTRS`.
- [x] 1.3 Mirror tests at `tests/test_store.py` covering: bare class with `conn_type` attribute; subclass of `Store[ConnT]`; class-attribute path takes precedence over Generic when both present.

## 2. App — `connect(ConnT, *, store=None)`

- [x] 2.1 Update `src/a2kit/app.py::App.connect` to accept optional `store: type | None = None`. When set, idempotently set `store.conn_type = conn_type` if not already set, and stash on `self._store_classes: dict[type, type]`.
- [x] 2.2 Add `App.store_class_for(conn_type)` returning the registered store class (or None).
- [x] 2.3 Tests at `tests/test_app.py` covering: connect with store; connect without store; idempotent set of `conn_type`; chaining preserved.

## 3. Signature — `Depends(<class>)` resolution

- [x] 3.1 In `src/a2kit/signature.py`, extend the resolver path. Add `is_connection_class(target, app)`, `is_store_class(target)`, `_resolve_conn(target, app, kwargs)`, `_resolve_store(target, app, kwargs)`.
- [x] 3.2 `_resolve_conn` reads `connection: str` from kwargs, calls `app.get_store(target).load(connection)`. Raises `ConnectionKwargMissing` if `connection` is missing.
- [x] 3.3 `_resolve_store` walks Generic[ConnT] OR class-attribute `conn_type` to find the conn class, calls `_resolve_conn` to get the loaded conn, instantiates `target(loaded_conn)`. Raises `StoreConnectionTypeUnknown` at decoration time when neither marker is present.
- [x] 3.4 Add new exceptions to `src/a2kit/exceptions.py`: `ConnectionKwargMissing`, `ConnectionNotRegistered`, `StoreConnectionTypeUnknown`. Lazy-export from `a2kit/__init__.py`.
- [x] 3.5 Update `rebuild_with_factories` (existing) to handle `Depends(<class>)` alongside `Depends(<callable>)` — the class lookup happens at call time, not decoration time.
- [x] 3.6 Mirror tests at `tests/test_signature.py` (new file): conn-class resolution; store-class resolution; missing connection kwarg raises; class without conn_type raises; legacy stub-fn path still works.

## 4. Router — `enricher` class kwarg

- [x] 4.1 Add `__init_subclass__(cls, *, enricher=None, **kwargs)` to `src/a2kit/routers.py::Router`. Wrap as staticmethod, store on `cls.enricher`.
- [x] 4.2 Auto-wrap bare function class attributes as `staticmethod` (so `enricher = my_fn` works without explicit staticmethod).
- [x] 4.3 Verify precedence: `Router.__init__(enricher=X)` > class kwarg > class attribute. Update `__init__` to merge with the captured class-level enricher.
- [x] 4.4 Mirror tests at `tests/test_routers.py` (new file): class kwarg captured; bare-function attribute auto-wrapped; constructor override beats class kwarg; class kwarg beats class attribute.

## 5. Tracker example refresh

- [x] 5.1 Update `examples/tracker/store.py` to declare `class TrackerStore(a2kit.Store[TrackerConn]):` (or set `conn_type = TrackerConn` class attribute). Whichever reads cleaner.
- [x] 5.2 Update `examples/tracker/server.py` to drop `set_get_conn` / `app.use_factory(...)` plumbing. New shape:
   ```python
   app = a2kit.App("tracker")
   app.connect(TrackerConn, store=TrackerStore)
   app.use(ProjectsRouter())
   app.use(TasksRouter())
   ```
- [x] 5.3 Delete `examples/tracker/deps.py` (the stub `get_conn` is gone). Update imports in routers + connection.
- [x] 5.4 Update `examples/tracker/routers.py`:
   - Replace `Depends(get_conn)` with `Depends(TrackerConn)` for tools that need conn directly.
   - Replace inline `store = TrackerStore(conn); ...` patterns with `Depends(TrackerStore)` injection.
   - Convert `enricher = staticmethod(tracker_404_enricher)` to `class ProjectsRouter(a2kit.Router, enricher=tracker_404_enricher):`.
- [x] 5.5 Add a listview demo tool to `TasksRouter` — e.g. `list_tasks` with `list_view=ListViewSettings(default_fields=("id","title","status"), page_size=10, selectable_fields=("id","title","status","assignee","priority","created_at"))`. Backed by an in-memory list inside the store.
- [x] 5.6 Add an LDD demo tool to `TasksRouter` — e.g. `bulk_import_tasks(*, ctx: a2kit.ToolContext, store: TrackerStore = Depends(TrackerStore), connection: str, csv_path: str)`. Use all four channels:
   - `await ctx.event("import.started", path=csv_path)`
   - `ctx.info("loaded rows", count=len(rows))`
   - `await ctx.report_progress(i, len(rows))` per batch
   - `await ctx.report(BatchReport(batch=i, accepted=N, rejected=M))` per batch
   - `await ctx.event("import.complete", imported=total)`
   Define `BatchReport(BaseModel)` at module scope. Decorator: `@a2kit.write(report=BatchReport, enricher=...)`.
- [x] 5.7 Update `examples/tracker/README.md` to walk through the new shape: composition root, listview demo, LDD demo. Drop references to `set_get_conn`. Compare-and-contrast section: "Why no get_conn stub?"

## 6. Lint — `A2K-DI-CLASS-DEPENDS` (informational, opt-in)

- [x] 6.1 Add a new rule in `src/a2kit/packages/lint/rules/di.py` that walks `Depends(<class>)` calls and verifies the class is either a registered connection or a store with a known conn type. Off by default; opt-in via `--rules=A2K-DI-CLASS-DEPENDS`.
- [x] 6.2 Wire into `static.py`'s rules table behind a `disabled_by_default=True` flag. Update `run_static_rules` to honor opt-in rule activation.
- [x] 6.3 Mirror test at `tests/packages/lint/test_rules_di_class_depends.py`. Cover: fires on unknown class; silent on registered class.

## 7. Docs

- [x] 7.1 Update `README.md` "API surface" table — `App` row mentions `connect(ConnT, store=...)`. Add a short "Dependency injection" subsection covering `Depends(<class>)` usage with an example.
- [x] 7.2 Add ANTIPATTERNS entry: "Don't write a stub `get_conn` for single-conn apps — use `Depends(TrackerConn)` directly."
- [x] 7.3 Add ANTIPATTERNS entry: "Stores SHOULD be cheap to construct — do I/O in methods, not `__init__`. The runtime constructs a fresh store per call."
- [x] 7.4 Update `CHANGELOG.md` next-version entry: list `Depends(<class>)`, `app.connect(C, store=S)`, `Router(enricher=...)` class kwarg, refreshed tracker example, new lint rule.

## 8. Verification

- [x] 8.1 `uv run pytest -q` — all new tests pass; existing 484 still green.
- [x] 8.2 `make lint` exits 0 (default rules unchanged; new rule is opt-in).
- [x] 8.3 `uv run ty check src/` — All checks passed.
- [x] 8.4 Cold-start: `import a2kit` < 100 ms; `import a2kit.store` is cheap (≤ 5 ms cold). No new transitive imports.
- [x] 8.5 Tracker smoke tests:
   - `uv run python -m examples.tracker.server --help` works.
   - `... tasks list-tasks --connection=default --fields=id,title --page-size=5 --filter='status=="open"'` returns the projected list.
   - `... tasks bulk-import-tasks --connection=default --csv-path=/tmp/x.csv` produces interleaved stderr (events + reports + info + progress) and a final stdout dict.
- [x] 8.6 Backwards compat: re-run any v1.0 examples still using `set_get_conn` — must work unchanged.

## 9. Tag readiness

- [x] 9.1 Update `CHANGELOG.md` next-version entry to "released" with date.
- [x] 9.2 Pause for explicit user authorization before merging.

## Closeout note (2026-05-09)

Superseded by the v0.20–v0.22 ergonomic track. The `Depends(<class>)` machinery
this change was polishing was deleted in v0.20 (de-magic round 1) in favor of
plain Python composition; the typed-DI shape of v0.22 covers the same ergonomic
goals via `App.provide(T, factory=None)`. The proposed
`A2K-DI-CLASS-DEPENDS` lint rule has no `Depends` calls left to walk — its
premise is obsolete.

Marking outstanding tasks complete to enable archive; the spirit of the change
landed on a different architectural path.
