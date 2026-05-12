## Context

`a2kit.App.singleton(T, factory)` registers a factory whose result is cached for the App's lifetime. The container fast-paths singleton resolution to a cache lookup once resolved. Today, the factory MUST be synchronous: `register_singleton` calls `inspect.iscoroutinefunction(factory)` and raises `ValueError` if true. Apps that need async-opened resources (SQLite via aiosqlite, Playwright browser, async LLM clients) work around this by hand-rolling a "lazy-init resource" class: sync `__init__`, internal `asyncio.Lock`, async `_ensure(self)`, every public method `await self._ensure()` first. The pattern is documented in `lazy-init-resources` and shipped uncoded by design.

a2web feedback (rounds 5 and 6) shows this pattern repeated three times in one app — `SqliteResource`, `BrowserPool`, `LlmExtractorResource` — at ~80 LOC total of double-checked-locking boilerplate. The container is already the natural place to do this exactly once. The pushback on a new `@app.async_resource` decorator was correct: it would fragment the surface. `singleton` is the right primitive; it just needs to accept the async shape.

The framework already runs in an async context: tool dispatch is `await`-able, `on_startup`/`on_shutdown` accept async handlers, and `container.apply_kwargs` is awaited where dispatch hooks need it. An async resolve path is not a foreign concept here.

## Goals / Non-Goals

**Goals:**

- `app.singleton(T, factory)` accepts both `Callable[[], T]` and `Callable[[], Awaitable[T]]` without any new keyword or decorator name.
- First resolution of an async-factory singleton awaits the factory exactly once, even under concurrent contention.
- Cached value is returned synchronously by `container.resolve(T)` after first resolution — no await tax on the hot path.
- Sync-factory singletons behave identically to today (zero regression, zero new code path on the hot path).
- The error message for sync `resolve` on a not-yet-resolved async singleton tells the user exactly where the async resolve path lives.

**Non-Goals:**

- No `@app.async_resource`, no `app.lazy_singleton`, no `app.aresource`, no new decorator of any name. The surface change is the type of `factory`'s second shape.
- No async `provide` (per-dispatch factories). `provide` stays sync — async per-dispatch factories are a different problem (and would cost an await per dispatch).
- No retroactive removal of the hand-rolled lazy-init pattern. Apps that need reconnect-on-failure or per-method re-entry guards can still write resource classes.
- No automatic shutdown wiring. Apps still close async resources via `@on_shutdown`. The container does not own `close()`.

## Decisions

### Decision 1: Accept the async factory shape on the existing `singleton` method

Detect `inspect.iscoroutinefunction(factory)` at registration time and store a flag on the singleton entry. Do not branch the public API.

**Alternatives considered:**

- *New `@app.async_resource(T)` decorator.* Explicitly rejected by user. Two names for one concept (cached, framework-owned, lifetime-bound) is the worst of both worlds: every consumer has to learn when to pick which, and the framework has two code paths to maintain.
- *Polymorphic factory that returns either `T` or `Awaitable[T]`, dispatched at resolve time on the return value.* Tempting (zero registration-time inspection), but it makes the type signature ambiguous (`Callable[[], T | Awaitable[T]]`) and forces the resolve path to inspect the return value on every call — including the cached one. Registration-time inspection is cheap and only happens once.

### Decision 2: Per-type `asyncio.Lock` for first-resolve coalescing

Maintain a `dict[type, asyncio.Lock]` on the container, created lazily on first async-singleton resolve. Inside the lock: re-check the cache (double-checked locking), and only call+await the factory if still unresolved.

**Alternatives considered:**

- *One container-wide lock.* Simpler, but serializes unrelated async first-touches (e.g. browser pool init blocks SQLite init). Per-type lock costs one dict entry per async singleton and unblocks unrelated init.
- *`asyncio.Event` instead of `Lock`.* Equivalent for "wait until ready" but more error-prone: you must remember to `set()` even on factory failure. `Lock` + double-checked-cache-read is the standard recipe.
- *No lock; rely on the event loop's single-threaded property.* Wrong. Two coroutines that both `await container.aresolve(T)` for the first time can both observe "not cached" and both run the factory; the awaits inside the factory yield control between them.

### Decision 3: Two resolution entry points — `resolve` (sync) and `aresolve` (async)

- `resolve(T)` for sync-factory singletons: unchanged. For async-factory singletons: returns the cached value if present; raises a precise error if not (because there's no sync way to await the factory).
- `aresolve(T)` (or whatever the existing async resolve path is named — `apply_kwargs` already has an async cousin): handles both shapes. For sync singletons, falls through to `resolve`. For async singletons, takes the per-type lock and awaits the factory on first call.

The framework's dispatch path uses `aresolve` (or, equivalently, `apply_kwargs` in its async variant). User code in tool methods continues to declare typed kwargs; the framework resolves them through the async path before calling the tool. So in practice, no user ever calls `aresolve` directly.

**Alternatives considered:**

- *Make `resolve` always async.* Massive churn; breaks every existing sync resolve call site; pays an await tax forever on the hot path.
- *Block the event loop with `loop.run_until_complete` inside sync `resolve`.* Hard NO. Re-entrant event loop calls are a footgun, and the framework dispatch already runs in an async context.

### Decision 4: Repositioning, not removal, of the `lazy-init-resources` spec

The hand-rolled pattern is still valid for cases the singleton can't cover: resources that need *per-method* lock semantics (e.g. reconnect on a broken connection), pools that re-init parts of themselves, things that want their own `close()` lifecycle separate from `@on_shutdown`. The spec is rewritten to lead with async-factory singletons and treat the hand-rolled pattern as an escape hatch.

**Alternatives considered:**

- *Archive `lazy-init-resources` entirely.* Loses the escape-hatch documentation. Some apps will legitimately need it.
- *Leave `lazy-init-resources` untouched.* Then consumers see two equally-recommended patterns and can't tell which to pick. The whole point of this change is to remove that confusion.

### Decision 5: No automatic resource teardown

The container holds cached instances and does not call `close()`. Apps still register `@on_shutdown async def _close(state): await state.sqlite.close()`. Reason: the container doesn't know how to close arbitrary types. Adding a `closer=` kwarg to `singleton(T, factory, closer=...)` would be a separate, larger surface change; this proposal keeps the surface change to exactly "factory may be async."

## Risks / Trade-offs

- *[Risk]* Apps that introspect the container during sync-only code paths can hit "async singleton not yet resolved" errors at non-obvious call sites. **Mitigation**: the framework triggers async-singleton resolution during startup warm-up (the existing `@on_startup` infrastructure), so by the time any tool dispatches, async singletons are already cached. The error path remains, with a message pointing at `@on_startup` warm-up.
- *[Risk]* Factory failure during first-resolve leaves the singleton in a "tried and failed" state; subsequent resolves will retry. **Mitigation**: this matches the existing sync-singleton behavior (a sync factory that raises is also retried on next resolve). Document explicitly.
- *[Risk]* Tests that mock the container may need to handle the async resolve path. **Mitigation**: in-process test client already runs in an async context; the existing test surface continues to work for sync factories, and async-factory tests use the async resolve path.
- *[Trade-off]* Per-type lock dict grows with the number of async singletons. **Acceptable**: O(number of async singletons), bounded and small.

## Migration Plan

- No user code changes required for sync-factory singletons.
- Apps with hand-rolled lazy-init resource classes can migrate one resource at a time: convert `_ensure` body into the factory, drop `_ensure` and the internal lock, register with `app.singleton(SqliteResource, build_sqlite_async)`. Old pattern continues to work; migration is opt-in.
- No rollback risk: the change is additive on the registration side (a previously-rejected factory shape now works). Only the error-contract spec changes are technically breaking.

## Open Questions

- Naming of the async resolve entry point: `aresolve`? Reuse an existing async path? Defer to implementation; spec only requires "there is an async path the framework uses, and sync `resolve` raises a precise error on unresolved async singletons."
