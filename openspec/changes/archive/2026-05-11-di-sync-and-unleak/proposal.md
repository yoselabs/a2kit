## Why

a2web's round-4 feedback (`A2KIT_FEEDBACK_v0.26.md`) surfaced four ergonomic gaps. Three of them (`Optional` fields on AppState, the lifecycle hook DI dance, the `container() is None` paper cut) are downstream of one architectural defect: **the DI container is async-aware, owns resource lifecycle, and hardcodes the magic name `"connection"` in its internals**. Each consumer pays for that in ceremony at the seam.

Audit also revealed a structural smell. The container lives at `packages/connections/container.py`, but it is the substrate used by `app.py`, health, tools, testing, and CLI dispatch. Naming the substrate after one of its consumers is the file-tree equivalent of putting numpy inside pandas. Three separate code paths in the container itself special-case the string `"connection"` (`container.py:310, 337, 401`), and `app.py:333` does the same. The container is not feature-agnostic; it just claims to be.

The single biggest move is to **shrink the container's job to what only a container can do** (typed lookups over already-constructed values), push async resource lifecycle to the consumer's composition site (lazy-init pattern), and route wire-string-to-typed-object resolution through the existing dispatch hook instead of through the container's magic-name branch. The container loses ~6x its line count; the App loses ~40% of its surface; the magic name leaves core.

This is a v0.27 breaking change. a2web is the only consumer using `app.singleton`/`app.provide` today (verified: `grep -rn "app.singleton" a2db a2atlassian` returns empty). No deprecation shim; hard cutover; a2web migrates alongside.

## What Changes

- **Relocate the DI container.** `packages/connections/container.py` → `a2kit/packages/di/container.py`. No consumer of the container imports `packages/connections` anymore. Connections becomes a peer consumer.
- **Strip async from the DI container.** One synchronous `resolve(T)` method. `resolve_sync` and `SyncResolveUnavailable` are deleted. `_SingletonWrapper`, lock coalescing, `_is_sync_chain`, `_first_async_dep`, `_factory_is_async`, `_resolve_factory_kwargs_sync`, the async resolve path: all deleted. Net deletion ~460 LOC inside the container.
- **Singleton factories MUST be synchronous.** `app.singleton(T, async_factory)` raises `ValueError` at registration time. Async resource initialization happens inside the resource class (lazy-init pattern) or at the composition root, not inside the DI container.
- **Document the lazy-init resource pattern.** No new framework primitive. Resources are plain classes with `async def open()`, `async def close()`, and async accessors that self-initialize on first call under an internal lock. AppState holds resource instances as non-Optional fields; locks live inside resources, not on state.
- **Move connection-string resolution to a dispatch hook.** Connection-aware apps install a hook (via `Connections.install(app)`) that resolves `wire_kwargs["connection"]` to the typed `ConnectionConfig` before the container sees the kwargs. The hook is async (it awaits `store.load`); the container is not. The string `"connection"` lives only in `packages/connections/`.
- **Remove `_reject_singleton_connection_dep` from core.** The rule it enforced is moot once core has no notion of "connection". A weaker, generic rule replaces it: singleton factories must be sync (which transitively rejects connection-dependent factories, since connection resolution is async).
- **Lifecycle hooks become DI-aware.** `@app.on_startup` and `@app.on_shutdown` accept signatures like `(state: AppState)` and resolve through `container.apply_kwargs`, matching `@app.health_check`. The legacy `(app: App)` signature is removed (breaking).
- **`App.container()` returns non-Optional.** The container is eager-initialized in `App.__init__`. The `container() is None` guard at every consumer site disappears.
- **Unify dispatch entry points.** `health.run_checks` switches from rolling its own DI invocation to calling `container.apply_kwargs(fn, {})`. One DI seam, three callers.

## Capabilities

### New Capabilities

- `di-container-package`: The DI container lives at `a2kit.packages.di` and is feature-agnostic. No reference to the names `connection`, `tracker`, or any other feature. Pure typed-map + factory-chain resolution.
- `connections-dispatch-hook`: The connections package installs a dispatch hook that resolves the wire `connection: str` to a typed `ConnectionConfig` before DI runs. The magic name lives in this hook, nowhere else.
- `lazy-init-resources`: Documented pattern for async-opened, sync-constructed resource classes. AppState fields stay non-Optional. Locks live inside resources.

### Modified Capabilities

- `request-scoped-di`: Drops async resolve, drops the `connection` parameter from `resolve`, drops `resolve_sync`. Adds the requirement that the container's public surface contains no feature-name references.
- `app-singletons`: Drops async-factory support. Drops the `_reject_singleton_connection_dep` rule (replaced by sync-only enforcement). Drops the requirement that singletons resolve via async chains.
- `app-lifecycle`: Lifecycle handlers are DI-aware. Handler signature `(app: App)` is removed in favor of typed-injection signatures.
- `core-composition`: `App.container()` returns `Container` (not `Container | None`).

### Removed Capabilities

None. All affected capabilities survive in modified form.

## Impact

- **API (breaking).**
  - `app.singleton(T, async_factory)` raises at registration. Consumers convert async factories to lazy-init resource classes.
  - `@app.on_startup` / `@app.on_shutdown` handlers accept typed kwargs, not `(app: App)`. Old signature removed.
  - `container.resolve(T, connection=...)` becomes `container.resolve(T)`. The connection kwarg is gone. Consumers that resolved manually rewire through the dispatch hook.
  - `container.resolve_sync` and `SyncResolveUnavailable` deleted.
  - `App.container()` returns non-Optional. Callers can drop the `is None` guard.
- **Code.** Net deletion ~600 LOC across `packages/connections/container.py` (~460), `app.py` (~80 in `_SingletonWrapper`, `_reject_singleton_connection_dep`), and `app-singletons`/`request-scoped-di` test surface. New code ~120 LOC (dispatch hook in connections, resource-pattern docs, container relocation glue).
- **a2web migration.** `state.py` rewrites: 4 `Optional` fields become non-Optional; 2 `Lock` fields delete (move into resources); `_event_payload` and `_emit` shim (~25 LOC) delete once typed emit ships (separate change). `server.py` lifecycle hooks lose the `container().resolve(...)` dance and accept `state: AppState`. `build_state` becomes a sync function. Resource classes (`SqliteResource`, `BrowserPoolResource`) gain `_lock`, `_ensure`, `async def open`, `async def close`. Estimated +60 LOC in resource classes, -30 LOC across state/server. Net ~30 LOC growth in a2web for permanent cleanup.
- **Cold start.** Improves marginally. The async-resolve path was never zero-cost.
- **Backwards compat.** None. Hard cutover at v0.27. No shim, no deprecation. The migration is mechanical.
- **Docs.** README "Composing an App" section rewrites. New "Resource pattern" appendix. The "v0.27 migration" note documents the four breaking changes with before/after diffs.
