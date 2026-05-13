# Design — singleton-teardown-topological

## D-WHY-NOT-REVERSE-REGISTRATION

The most common manual pattern — `for closer in reversed(closers):` —
is wrong in the general case. Concrete failure mode:

```
Registration order:
  app.singleton(BrowserPool, build_pool)   # factory needs DB handle
  app.singleton(SqliteResource, build_sql) # registered second

DI graph:
  build_pool needs SqliteResource → BrowserPool depends on SqliteResource

Reverse-of-registration teardown order:
  1. close(SqliteResource)   # ← closes DB
  2. close(BrowserPool)      # ← tries to flush cookies to closed DB → crash
```

The right discipline reads the *resolved DI graph*, not the
*registration order*. Topological sort with dependents-first
ordering: walk from "leaf" singletons (no other singleton depends on
them) outward.

## D-TOPO-ALGORITHM

The container already builds the forward dependency edges via
`_collect_reachable` (`di/container.py:229`). We need the *reverse*
edges for teardown ordering. Algorithm:

1. Collect the set `S` of types that are registered singletons AND
   resolved (cached instance != `_UNRESOLVED`) AND carry a teardown
   callback.
2. Build a forward-edge map `deps: T → set[T']` where each `T'` is
   a singleton in `S` that `T`'s factory depends on. Use the
   container's `_params_for(factory)` to walk one layer; only count
   annotations that resolve to another type in `S`.
3. Kahn's algorithm with deterministic tiebreaker on
   `(id(T), registration_index)`:
   - Start with the queue of types in `S` that **no other type in S
     depends on** (i.e. their forward-edge in `deps` from any other
     `T` is empty — these are the dependents).
   - Pop one; emit it; remove its outgoing edges from `deps`.
   - Repeat until `deps` is empty or stalled.
4. If stalled (cycle), break by emitting the lowest-id type and
   continuing; emit a `WARN` log line `"singleton teardown cycle
   detected: <cycle>; breaking at <type>"`.

Output: a list of types in **emission order**, which IS the teardown
order. Dependents are emitted first → torn down first.

```python
def teardown_order(self) -> list[type]:
    candidates = [
        t for t in self._singletons
        if self._singletons[t] is not _UNRESOLVED
        and t in self._teardowns
    ]
    # Forward-edge map (T → singletons in candidates that T depends on)
    deps: dict[type, set[type]] = {t: set() for t in candidates}
    candidate_set = set(candidates)
    for t in candidates:
        factory = self._providers.get(t)
        if factory is None:
            continue
        for spec in self._params_for(factory):
            if spec.annotation in candidate_set:
                deps[t].add(spec.annotation)
    # Reverse edges: T' → {T : T depends on T'} (i.e. T' is depended-on-by T)
    depended_on_by: dict[type, set[type]] = {t: set() for t in candidates}
    for t, ds in deps.items():
        for d in ds:
            depended_on_by[d].add(t)
    # Emit dependents first: types with no incoming "depended on by" edges
    # are leaves of the reverse-edge graph.
    order: list[type] = []
    remaining = set(candidates)
    while remaining:
        ready = sorted(
            (t for t in remaining if not (depended_on_by[t] & remaining)),
            key=lambda t: id(t),
        )
        if not ready:
            # Cycle — break deterministically.
            cycle = sorted(remaining, key=lambda t: id(t))
            _log.warning("singleton teardown cycle: %s; breaking at %s",
                         [t.__name__ for t in cycle], cycle[0].__name__)
            ready = [cycle[0]]
        for t in ready:
            order.append(t)
            remaining.discard(t)
    return order
```

## D-ERROR-ISOLATION — LDD error log + continue

Each teardown call runs under a `try/except Exception`. On
exception:

- The error is **not re-raised** — sibling teardowns continue.
- An LDD `error`-level log line is emitted with `class`, `message`,
  and the singleton type name in fields. The LDD scope is no longer
  active by the time shutdown runs, so this routes through the
  `_log.error` Python logger fallback (per `a2kit.ldd.log`'s
  ambient-state guard) — visible in CLI stderr, structured via
  the standard logging handler chain.
- The full traceback is logged at DEBUG level (via
  `logging.exception`).

`A2KitSingletonTeardownError` aggregates all failures into a single
exception attribute (`.failures: list[tuple[type, Exception]]`) for
callers who want programmatic introspection. The exception is **not
raised** — it's stashed on `App.teardown_failures` (a new attribute,
empty list when shutdown is clean) for tests and post-mortem.

## D-LIFESPAN-COMPOSITION — innermost on shutdown

Current `lifespan_cm()` composes user lifespan + Router lifespans
via `a2kit.lifespan.compose`. Add a synthetic "framework teardowns"
leg that wraps the composition:

```python
def lifespan_cm(self):
    inner_legs = [self._lifespan] if self._lifespan else []
    inner_legs.extend(_router_lifespan_factory(r) for r in self._router_lifespans)
    if inner_legs:
        composed = _compose(*inner_legs)
        return self._wrap_with_teardowns(composed(self))
    return self._wrap_with_teardowns(nullcontext())

@asynccontextmanager
async def _wrap_with_teardowns(self, inner_cm):
    async with inner_cm as user_state:
        yield user_state
    # Reached after user/Router lifespans have fully exited.
    await self._run_teardowns()
```

Order on shutdown (innermost to outermost):
1. User `finally`/Router `finally` blocks run inside their own scope.
2. After all user/Router lifespans exit, `_run_teardowns()` walks
   `container.teardown_order()` and closes each registered singleton.

This means user code can still hand-roll teardowns (which run first,
inside their own scope) while the framework provides the safety net
for explicitly-registered teardowns (which run after).

## D-SYNC-VS-ASYNC-TEARDOWN

`teardown` accepts either form:

```python
app.singleton(R, build_r, teardown=lambda r: r.close())   # sync
app.singleton(R, build_r, teardown=lambda r: r.aclose())  # async (returns coroutine)
```

`_run_teardowns` checks each call's return:

```python
result = teardown_fn(instance)
if inspect.isawaitable(result):
    await result
```

Same convention as `dispatch_hook` handling at
`container.py:289-291`.

## D-CYCLE-HANDLING

DI graphs SHOULD be acyclic. The container's existing resolution
chain detection (`chain: list[type]` parameter, raises on cycle)
already prevents *resolution-time* cycles. But the teardown graph is
a different beast: A may depend on B at construction time but B
might hold a reference to A at runtime (via injection). For
teardown ordering, what matters is the *factory parameter graph*,
not the runtime reference graph.

Cycle in the factory parameter graph IS prevented by the existing
resolution-cycle check. So a cycle in `teardown_order()` indicates
a registration-order anomaly the container should have caught
earlier. The defensive break + WARN is belt-and-suspenders, not the
load-bearing safety.

## Alternatives considered

### Alt-A — reverse-of-registration

Rejected per D-WHY-NOT-REVERSE-REGISTRATION. The pool↔sqlite
counter-example is realistic.

### Alt-B — caller-supplied teardown order

`app.singleton(T, factory, teardown=fn, teardown_priority=10)` —
caller picks the integer. Rejected: forces every consumer to
re-derive the DI graph mentally; the framework already has the
information.

### Alt-C — teardown hook on the resource class

Sniff `instance.close()` / `instance.aclose()` by attribute and
invoke automatically. Rejected: implicit; conflicts with resources
that have those methods but don't want auto-invocation (e.g.
hand-managed pools).

### Alt-D — propagate first teardown failure

Re-raise the first teardown exception after running siblings.
Rejected: a shutdown failure should not mask the original cause of
shutdown (the original `KeyboardInterrupt`, the original
`HTTPError` from a tool body). Errors are surfaced via LDD log +
`App.teardown_failures` attribute.

## Risks

- **Routers contributing singletons via `providers: ClassVar`**: a
  Router-installed provider isn't necessarily a singleton with a
  teardown. The check operates on `_teardowns` membership, so
  router providers without teardowns are correctly ignored.
- **Async-factory singletons**: factories run on first resolve. By
  the time `_run_teardowns` fires, all resolved singletons have
  their cached instances; the teardown receives the instance, not
  the factory. Behaviour identical for sync and async factories.
- **App used without lifespan**: today, `lifespan_cm()` returns
  `nullcontext()` when no user/Router lifespan is registered. With
  this change, `_run_teardowns` should still fire if any teardown
  is registered. Fix: always compose `_wrap_with_teardowns`,
  return it unconditionally when there's at least one teardown
  registered.

## Out of scope

- Sync-context-manager teardown (`__exit__`).
- Per-call teardown registration.
- Resource state machine (started → stopping → stopped).
