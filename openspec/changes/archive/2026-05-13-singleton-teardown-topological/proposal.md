# Framework-owned singleton teardown with topological ordering

## Why

Every a2kit consumer with async-opened resources (DB pools, HTTP
clients, browser handles, LLM clients) hand-rolls the same shutdown
pattern in their lifespan body's `finally`:

```python
@asynccontextmanager
async def lifespan(app):
    state = app.container().resolve(AppState)
    await state.sqlite._ensure()
    try:
        yield
    finally:
        for closer in (state.llm_extractor.close, state.browser_pool.close, state.sqlite.close):
            try:
                await closer()
            except Exception:
                pass  # ← swallows errors silently
```

Three problems compound:

1. **Repetitive boilerplate.** Each resource adds one line; scales
   linearly with resource count.
2. **Silent error masking.** `try/except: pass` is the most common
   shape; failures during shutdown vanish with no log, no LDD event,
   no traceback.
3. **Wrong ordering.** Reverse-of-registration (the most common manual
   pattern) is *incorrect* in the general case. If `BrowserPool`
   depends on `SqliteResource` (e.g. for cookie persistence) but was
   registered first because the pool's factory needs a DB handle,
   reverse-of-registration tears down sqlite BEFORE the pool —
   `pool.close()` then hits a closed DB. The correct discipline is
   **topological sort over the resolved DI graph**: dependents before
   dependencies.

The current `app.singleton(T, factory)` docstring already anticipates
the `teardown=` parameter: *"Method-call form is the only path (v0.33):
the decorator form ``@app.singleton(T)`` was removed to free the
signature for the upcoming ``teardown=`` parameter."* This change
delivers it.

## What Changes

- `App.singleton` gains an optional `teardown: Callable[[T], Any] | None`
  keyword argument: `app.singleton(SqliteResource, build_sqlite,
  teardown=lambda r: r.close())`.

- `Container.register_singleton` stores the optional teardown callback
  alongside the factory.

- New `Container.teardown_order()` walks the resolved-singleton subset
  of the DI graph (via the existing `_collect_reachable` helper) and
  returns types in **reverse-topological order** (dependents first,
  then their dependencies). Pure types with no provider edges are
  preserved in registration order as the tiebreaker.

- New `App._run_teardowns()` (async) iterates
  `container.teardown_order()`, for each resolved singleton with a
  registered teardown:
  - calls the teardown (awaits if it returns an awaitable),
  - catches `Exception` (not `BaseException`),
  - on exception, emits an LDD `error` log line with `class`,
    `message`, and the singleton type name; continues to the next
    teardown (error-isolated, no cascade).

- `App.lifespan_cm()` composes `_run_teardowns()` as the **last leg**
  (innermost on shutdown) of the composed lifespan, after user
  lifespan and Router lifespans. So shutdown order is:
  1. Innermost user/Router `finally` blocks run (in their own scope).
  2. App's `_run_teardowns` walks the DI graph in reverse topological
     order, closing every singleton with a registered teardown.

- New diagnostic: `A2KitSingletonTeardownError` wraps cascaded
  teardown failures for any caller who wants to inspect what failed
  (the LDD log line is the primary surface; the exception is for
  programmatic introspection).

- Cycle handling: if the DI graph contains a cycle among singletons
  with teardowns, topological sort breaks the cycle deterministically
  (lowest-id type wins) and emits a `WARN`-level log line per cycle.

## Impact

- **Affected specs**: `app-singletons` — adds requirement *"App.singleton
  accepts `teardown=` for framework-managed shutdown"* with scenarios for
  ordering, error isolation, and cycle handling.
- **Affected code**:
  - `src/a2kit/app.py` — `singleton(...)` signature accepts `teardown=`;
    `_run_teardowns()` helper; `lifespan_cm()` composition.
  - `src/a2kit/packages/di/container.py` — `register_singleton(...)`
    accepts teardown; `_teardowns: dict[type, Callable]`;
    `teardown_order()` topological walk.
  - `src/a2kit/exceptions.py` — `A2KitSingletonTeardownError`.
  - `OPERATIONAL_CONTRACTS.md` — new section "Q-Teardown: Singleton
    teardown contract" documenting ordering, error isolation, and the
    LDD `error` log line on failure.
  - `tests/test_singleton_teardown.py` — new file. Cases: simple
    teardown fires; topological ordering (pool→sqlite); error
    isolation (one teardown raises, others still run); LDD error
    log captured; cycle warning.
- **APIs**: NON-BREAKING. Default `teardown=None` preserves current
  behaviour (no teardown registered, no auto-shutdown invocation).
- **Dependencies**: none.
- **CI cost**: ~6 new tests; negligible.
- **Risk**:
  - **Order-dependent consumers**: any caller currently relying on
    reverse-of-registration order in their *own* `finally` block stays
    in control — they don't pass `teardown=` and continue managing it
    by hand. The new mechanism is additive.
  - **Cycle in DI graph**: handled with deterministic break + WARN
    log; documented in design.
  - **Teardown raising**: error-isolated by contract. Tests pin that
    a raising teardown does not abort sibling teardowns.
- **Out of scope**:
  - Sync `Container.resolve`-time teardown registration (not a thing —
    teardowns are App-lifecycle scoped).
  - Per-request teardown (request-scoped resources are not singletons).
  - Topological ordering of *user* / *Router* lifespan legs against
    the framework teardowns (Router legs run innermost in user scope;
    framework teardowns run after).
