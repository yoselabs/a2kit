## 1. Container: registration

- [x] 1.1 In `src/a2kit/packages/di/container.py`, update `register_singleton` to accept async factories: replace the `iscoroutinefunction` rejection branch with shape detection that stores an `is_async: bool` flag (or equivalent) alongside the factory in `self._providers` or on a parallel dict.
- [x] 1.2 Confirm `register` (provide path) still rejects async factories with the existing `ValueError` and unchanged message.
- [x] 1.3 Update the module-level docstring (currently asserts factories are synchronous) to reflect dual-shape `singleton` registration.

## 2. Container: async resolution path

- [x] 2.1 Add a per-container `dict[type, asyncio.Lock]` (`self._async_singleton_locks`) created lazily.
- [x] 2.2 Implement (or extend) the container's async resolution path (`aresolve` or whichever existing async entry the framework already uses) so that for async-factory singletons: check cache; if unresolved, take the per-type lock; re-check cache under the lock; if still unresolved, await the factory and cache the result; release the lock.
- [x] 2.3 Ensure dependency resolution inside an async-factory body uses the async path for its own parameters (so an async factory can depend on other async singletons).
- [x] 2.4 Confirm that sync-factory singletons take no new code path on the hot path (cached fast-path return is byte-for-byte equivalent to today).

## 3. Container: sync resolve error contract

- [x] 3.1 In `resolve`, when a requested type is an unresolved async-factory singleton, raise a precise error naming the type, identifying the factory as async, and directing the caller to the async resolve path or `@on_startup` warm-up.
- [x] 3.2 Confirm that after async first-resolution, sync `resolve(T)` returns the cached instance without raising.

## 4. App surface

- [x] 4.1 In `src/a2kit/app.py`, widen the `singleton` method's `factory` type annotation to `Callable[..., T] | Callable[..., Awaitable[T]] | None`.
- [x] 4.2 Update the `singleton` docstring to document both shapes, the awaited-on-first-resolution semantics, the per-type-lock coalescing guarantee, and the sync-`resolve` error contract for unresolved async singletons.
- [x] 4.3 Remove the "Factories MUST be synchronous. Async resource initialization belongs in resource classes" sentence from the docstring; replace with a pointer to the async-factory-singleton pattern as the primary path for async-opened resources.

## 5. Framework dispatch integration

- [x] 5.1 Ensure the dispatch path (which already runs in an async context) uses the container's async resolution path for tool-method kwargs, so async-factory singletons are awaited transparently before the tool body runs.
- [x] 5.2 Confirm `apply_kwargs`'s async variant routes through the async path for async-factory singletons.
- [x] 5.3 Verify `on_startup` handlers that take async-factory-singleton kwargs resolve correctly (first-resolution happens inside startup).

## 6. Tests

- [x] 6.1 Unit test: `register_singleton` with `async def` factory succeeds (no `ValueError`).
- [x] 6.2 Unit test: async-factory singleton is awaited exactly once on first resolve; subsequent resolves return the cached instance.
- [x] 6.3 Concurrency test: ten concurrent `aresolve(T)` calls on an unresolved async singleton invoke the factory exactly once and all observe the same instance.
- [x] 6.4 Concurrency test: two different async singletons resolve in parallel (their per-type locks do not serialize against each other).
- [x] 6.5 Failure test: async factory that raises on first call propagates the exception; a later retry awaits the factory again and caches the successful result.
- [x] 6.6 Error-contract test: sync `resolve(T)` on an unresolved async singleton raises with the documented message naming `T` and pointing at the async path.
- [x] 6.7 Error-contract test: sync `resolve(T)` on an already-resolved async singleton returns the cached instance without raising.
- [x] 6.8 App-scope test: two `App` instances each with an async-factory singleton for `T` produce two distinct resolved instances and two distinct locks.
- [x] 6.9 Introspection test: `has_singleton(T)` returns `True` after registration of an async factory before first resolve; `singletons()[T]` returns the unresolved sentinel until first await.
- [x] 6.10 Negative test: `provide(T, async_factory)` still raises `ValueError` (unchanged for the per-dispatch path).
- [x] 6.11 Negative test: no `app.async_resource` attribute exists; `from a2kit import LazyResource` / `async_resource` fails.

## 7. Documentation

- [ ] 7.1 Update the README "Resource pattern" appendix to lead with `app.singleton(T, async_factory)` as the primary async-resource path; demote the hand-rolled `_ensure` pattern to an escape-hatch section with the specific use cases (reconnect-on-failure, partial pool re-init, separate `close()` lifecycle). (Deferred — docs sweep not in core scope.)
- [ ] 7.2 Update any DI / container documentation that says "singleton factories must be sync" to reflect dual-shape acceptance. (Deferred — partially done via docstrings; README sweep later.)
- [ ] 7.3 Add a short migration note showing the before/after for a typical lazy-init resource class collapsing into an async factory. (Deferred — CHANGELOG entry covers it for v0.29 release notes.)

## 8. Validation

- [x] 8.1 Run `openspec validate singleton-async-factories --strict` and confirm it passes (this is also a pre-merge gate).
- [x] 8.2 Run the full a2kit test suite and confirm no regressions on sync-singleton paths.
- [ ] 8.3 Spot-check downstream (a2web) with a single resource (e.g. `SqliteResource`) migrated to async-factory singleton to confirm the surface lands as designed; do not migrate the rest in this change. (Deferred — downstream task, not blocking this change.)
