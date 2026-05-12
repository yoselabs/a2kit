## Why

Apps using `a2kit` for async-opened resources (SQLite, browser pools, LLM clients) currently hand-roll a "lazy-init resource" class per resource: sync `__init__`, internal `asyncio.Lock`, async `_ensure`, every method awaits `_ensure` first, idempotent `close`. In a2web this is roughly 80 LOC of double-checked-locking boilerplate across `SqliteResource`, `BrowserPool`, and `LlmExtractorResource`, repeated across every consumer. Round-5 feedback flagged this as a gap; round-6 confirmed it still hurts. The container already caches singletons exactly once; if it also awaited async factories on first resolve under a lock, the resource class collapses to its async business methods plus `close`. No new public surface needs to be invented; the existing `app.singleton(T, factory)` signature simply admits one more factory shape.

## What Changes

- Extend `App.singleton(T, factory)` to accept either a sync factory `Callable[[], T]` or an async factory `Callable[[], Awaitable[T]]`. The container inspects the factory at registration time and remembers the shape.
- On first resolve of an async-factory singleton, the container awaits the factory under a per-type `asyncio.Lock` and caches the resolved instance. Subsequent resolves return the cached instance synchronously — no await, no lock.
- Concurrent first-touch is coalesced: N concurrent awaiters share one factory invocation; the factory runs exactly once.
- `container.resolve(T)` continues to be synchronous for sync-factory singletons. For async-factory singletons, resolution before the first `await container.aresolve(T)` (or framework-internal async resolution) raises a precise error directing the user to the async resolve path. The framework dispatch already runs in an async context, so this is the natural call site.
- **BREAKING (for error contract only)**: `singleton(T, async_factory)` no longer raises `ValueError` at registration. The "async factories rejected" rule is removed from `app-singletons` and `request-scoped-di`. Apps that relied on the early-rejection error message must adapt; no working code path breaks.
- The `lazy-init-resources` capability is repositioned: the round-5 hand-rolled-resource pattern is now superseded by async-factory singletons for the common case. The spec documents async-factory singletons as the preferred path and keeps the hand-rolled pattern only for cases that legitimately need per-method re-entry guards (e.g. reconnect-on-failure semantics) — which is a narrow minority.
- **No new decorator.** The proposal explicitly does NOT introduce `@app.async_resource`, `@app.lazy`, or any sibling name. The dual-shape `singleton` is the entire surface change.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `app-singletons`: `singleton(T, factory)` accepts async factories; the "MUST be synchronous" / "async raises ValueError" requirements are replaced with dual-shape acceptance, concurrency-safe first-resolve, and async resolution semantics.
- `lazy-init-resources`: the pattern is demoted from "the recommended path for async-opened resources" to "an escape hatch for resources that need per-method re-entry guards"; async-factory singletons become the primary documented path.
- `request-scoped-di`: the scenario rejecting async factories on `provide`/`singleton` is narrowed to apply only to `provide` (per-dispatch factories remain sync).

## Impact

- `src/a2kit/app.py`: `singleton` docstring and signature widen; no other behavior change.
- `src/a2kit/packages/di/container.py`: `register_singleton` accepts async factories; `resolve` short-circuits cached async-singleton values; a new async resolve path (`aresolve` or equivalent) awaits async factories under a per-type lock on first call.
- Framework dispatch (the call site that already runs async): on startup-warmup or first tool dispatch, the framework triggers async-singleton resolution through the async path before sync `resolve` runs.
- a2web (downstream): `SqliteResource`, `BrowserPool`, `LlmExtractorResource` can shed their `_ensure` plumbing in favor of `app.singleton(SqliteResource, build_sqlite)` where `build_sqlite` is `async def`. Out of scope for this change.
- No changes to MCP wire format, tool contracts, or LDD.
