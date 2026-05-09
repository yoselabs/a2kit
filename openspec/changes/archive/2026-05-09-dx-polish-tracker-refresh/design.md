## Context

The v1.0 tracker example was the canonical first-impression surface
for a2kit. Three rough edges accumulated during the v1-cleanup-debt
pass and the v1.0 thin-core split:

1. The connection-injection contract requires three identifiers
   (`get_conn` stub, `get_conn_factory`, `app.use_factory(... as_=get_conn)`)
   for what semantically is one fact: "this tool needs a TrackerConn."
2. Stores are reconstructed in every tool body. Multiple tools that
   read application state repeat `store = TrackerStore(conn);
   projects, tasks = store.load_state()` boilerplate.
3. Router-level enrichers require `staticmethod` to dodge the
   descriptor protocol. Mechanical noise that appears in the cleanest
   demo we have.

In addition, the tracker example doesn't yet showcase listview
adaptability (an opt-in v1.0 kit) or LDD (the four-channel ToolContext
surface that just shipped in `ldd-streaming-reports`). Both are core
v1.0 features that lack first-class demonstration in the canonical
example.

This change polishes the public surface around DI for connection /
store classes, fixes the enricher class-kwarg ergonomics, and refreshes
the tracker example to demonstrate the full v1.0 surface.

### Constraints

- **Backwards compatibility is mandatory.** All existing patterns
  (stub `get_conn` + `use_factory`, `enricher = staticmethod(fn)`,
  `__init__(enricher=...)`) continue to work unchanged. The new
  shapes are additive.
- **No new transitive imports at cold-start.** The class-resolution
  logic lives in `signature.py` (already loaded). Verified via the
  existing cold-start test.
- **No FastMCP coupling.** The DI changes happen entirely in the
  protocol-neutral core; both adapters (MCP and CLI) inherit the new
  behavior without modification.
- **Plain Python classes.** Stores are not Pydantic models, not
  registries — just classes with a `conn_type` attribute or a
  `Generic[ConnT]` parameter. No new dependency.

## Goals / Non-Goals

**Goals:**
- `Depends(TrackerConn)` works without a stub function.
- `Depends(TrackerStore)` works with one extra registration.
- `class TasksRouter(a2kit.Router, enricher=fn):` works.
- Tracker example refreshed: removes stub plumbing, adds listview kit
  demo, adds LDD demo, replaces `staticmethod(...)` enricher.
- One canonical example: anyone reading `examples/tracker/` sees the
  full v1.0 surface in working code.

**Non-Goals:**
- Pushdown adapters (filed as `pushdown-listview`; this change uses
  the existing post-hoc listview kit).
- Per-tool store overrides (tools that want a non-default store can
  still construct it manually inside the body — not common enough to
  earn DI shape).
- Async store construction. Stores SHOULD be sync `__init__`. Any
  async work belongs in store methods.
- Removing the legacy stub-function path. Backwards-compat is mandatory
  and the legacy path is fine for advanced cases (multi-tenant factory
  swaps, test overrides via `app.use_factory(...)`).

## Decisions

### Decision 1: `Depends(<class>)` is the new canonical key

Considered three forms (see proposal Q&A):

- **Option A: `Depends(TrackerConn)` (chosen).** Class IS the key.
  Reads naturally; one identifier; type-safe (the kwarg is typed
  `TrackerConn` already). Discoverable: a reader sees the type and the
  Depends in one line and understands "this is auto-injected from the
  registered class."
- **Option B: Auto from type, no Depends.** Most magical — drops the
  marker. Rejected because FastMCP signature introspection would
  surface `TrackerConn` as a tool-input field. The Depends marker is
  what tells `strip_dependencies` to remove the kwarg before schema
  generation.
- **Option C: Stub-function fallback.** Backwards-compat win, but
  doesn't address the "stub is noise" complaint.

Option A wins. The `Depends` marker stays as the auto-inject signal
(consistent with `uncalled_for`'s parameter-default contract); the
*value* of `Depends(...)` is now optionally a class.

### Decision 2: Store classes declare their conn type, not the App registers per-tool

Considered two binding shapes:

- **Per-class declaration (chosen).** `TrackerStore.conn_type = TrackerConn`
  OR `class TrackerStore(Store[TrackerConn]):`. The store knows what it
  wraps; the App just registers connection classes. Decentralized:
  store authors don't depend on the App's registration order.
- **Per-app registration.** `app.connect(TrackerConn).bind_store(TrackerStore)`.
  Centralized but creates an "is this store registered for this app?"
  question that doesn't exist with per-class declaration.

The chosen shape composes: stores can be declared in a library, used
in any App that registers their conn class. `app.connect(C, store=S)` is
sugar that sets `S.conn_type = C` if not already set — saves a line for
the common single-store-per-conn case.

### Decision 3: Generic[ConnT] is the preferred form; class attribute is fallback

For new code, `class TrackerStore(Store[TrackerConn]):` is recommended:
the type system already sees the binding, no runtime-only attribute. We
introspect via `typing.get_args(typing.get_origin(orig_bases[0]))`.

For existing code or non-generic stores, `conn_type: type[ConnT] = TrackerConn`
class attribute also works — easier to retrofit. We check the attribute
first, fall back to the Generic parameter.

A new lightweight `a2kit.Store` Protocol-like base ships in
`src/a2kit/store.py` with the Generic parameter. It's a marker class:
no methods, no init magic, just a type-system anchor. Stores don't have
to inherit it — the class-attribute path stays first-class.

### Decision 4: Router enricher kwarg via PEP 487 `__init_subclass__`

```python
class Router:
    def __init_subclass__(cls, *, enricher=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if enricher is not None:
            cls.enricher = staticmethod(enricher)
```

Three forms now coexist:

| Form | Where it lives | When it fires |
|---|---|---|
| `class TasksRouter(a2kit.Router, enricher=fn):` | class header | subclass definition |
| `enricher = staticmethod(fn)` (or bare `enricher = fn`) | class body | subclass definition |
| `TasksRouter(enricher=fn)` | constructor | router instance |

Precedence: constructor > class kwarg > class attribute. The new path
also auto-wraps a bare function attribute as `staticmethod` so authors
don't have to write `staticmethod(...)` themselves.

### Decision 5: Resolution happens in `strip_dependencies` / signature pass

Today `strip_dependencies` removes `Depends(...)` kwargs before schema
generation. We extend it: when the `Depends`'s value is a registered
connection or store class, the runtime resolves it at call time the
same way it currently resolves stub-function `Depends`. The dispatch
table grows by two entries:

```python
def _resolve_depends(d, app, kwargs):
    target = d.dependency  # uncalled_for stores the callable here
    if inspect.isclass(target):
        if target in app._connection_types:
            return _resolve_conn(target, app, kwargs)
        if hasattr(target, "conn_type") or _is_generic_store(target):
            return _resolve_store(target, app, kwargs)
        raise ConnectionNotRegistered(target)
    return target(**filtered_kwargs)  # legacy callable path
```

### Decision 6: Demo-level changes drive the API shape, not the other way around

The tracker example's pain is the source of truth. The proposal exists
because reading the example felt clunky. Every change to the public
surface is justified by "the example reads better after this."
Anti-decision: do not add abstractions that the example doesn't use.
If a feature doesn't show up in the refreshed tracker, it doesn't ship
in this change.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `Depends(<class>)` collides with future `Annotated` forms | Documented: parameter-default form is the only supported DI shape (existing rule A2K-DI-ANNOTATED). |
| Stores with expensive `__init__` slow tools down | Documented in README + ANTIPATTERNS: "Stores SHOULD be cheap to construct; do I/O in methods, not __init__." |
| Author confusion: which Depends form to use? | README "Migration" section frames it: legacy stub-fn path = "swap to factory at runtime" use case (multi-tenant, tests). Class form = "single conn type" common case. |
| `Generic[ConnT]` introspection edge cases | Class-attribute path is the always-available fallback. We document both. |
| `__init_subclass__` interaction with other base classes | Tests cover multiple-inheritance scenarios. Standard PEP 487 `**kwargs` forwarding ensures cooperation. |

## Migration

The refreshed tracker is the migration guide. No deprecation warnings,
no compat shims to remove later — both shapes coexist permanently.

```python
# v1.0 (still works):
async def get_conn(*, connection: str) -> TrackerConn: ...
app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)
# tool: conn: TrackerConn = Depends(get_conn)

# After this change (recommended):
app.connect(TrackerConn, store=TrackerStore)
# tool: conn: TrackerConn = Depends(TrackerConn)
# OR:    store: TrackerStore = Depends(TrackerStore)
```

```python
# v1.0 (still works):
class TasksRouter(a2kit.Router):
    enricher = staticmethod(tracker_404_enricher)

# After this change (recommended):
class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):
    ...
```

## Open Questions

- Should `app.connect(...)` accept multiple stores per conn? E.g.
  `app.connect(C, stores=[S1, S2])` for apps that have two store classes
  wrapping the same conn. Defer until a real use case shows up; current
  shape supports it via direct `S.conn_type = C` declaration.
- Should the resolution path memoize the resolved store class lookup
  per-call? Trivial perf optimization; defer until benchmarks show
  it matters.
- Should we ship a `@a2kit.store` decorator that captures `conn_type`
  via a kwarg? E.g. `@a2kit.store(conn=TrackerConn) class TrackerStore:`.
  Symmetric to the verb decorators; defer pending demand.
