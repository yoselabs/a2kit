# Design — di-sync-and-unleak

## Context

Three threads converged during a2web round-4 review:

1. **DI consistency.** `@health_check` is DI-aware (resolves via `app._dispatch_hook`). `@on_startup` is not (passes bare `App`, forces `container().resolve()` dance). One model, applied unevenly.
2. **Async in DI.** `_SingletonWrapper` supports async factories with lock coalescing. `Container.resolve` is async. `resolve_sync` exists with `SyncResolveUnavailable` for callers that can't await. The container carries two execution paths and bifurcates every consumer.
3. **The `connection` leak.** `Container.resolve` takes `connection: str | None`. `partition_kwargs` returns a tuple whose third slot is `needs_connection: bool`. Four sites pattern-match the string `"connection"`. `app.py` reaches into `container._chain_reaches_connection`. The container is named after one of its consumers (`packages/connections/container.py`).

The conversation that produced this change traced these threads to one root: **the container is doing too much.** It owns async lifecycle, knows feature names, and bifurcates sync/async resolution. Each of those is a tax. The design below pulls each tax out.

## Decision 1: Container is synchronous, period

**Decision.** `Container.resolve(T) -> T` is sync. There is no async variant. Singleton factories must be sync. Provider factories must be sync.

**Rationale.** Audit of what async-in-DI buys today:

| Async-DI use site | Why async? | Could it be sync? |
|---|---|---|
| Connection store load | reads file/decrypts | yes (store has sync API) |
| ConnectionConfig per-call | awaits store load | yes if store is sync |
| AppState.sqlite construction | aiosqlite.connect | no, but moves out of DI |
| AppState.browser_pool | Camoufox `__aenter__` | no, but moves out of DI |
| AppState.llm_extractor | httpx.AsyncClient | no, but moves out of DI |
| Singleton lock coalescing | only for above | irrelevant if above moved |

Async resource initialization has exactly one legitimate home: **inside the resource class**, behind a lazy accessor. Pushing it there lets the container be sync, dict-like, and ~80 LOC. The connection-load case moves to a dispatch hook (Decision 4).

**Alternatives considered.**

- *Path B (lifespan + sync DI).* Resources opened at composition root via `async with build_state() as state: app.container[AppState] = state`. Works, but introduces a composition-root pattern the consumer must learn.
- *Path A (status quo + ergonomic polish).* Keep async DI, just add the lifespan-factory `AsyncIterator` shape. Pays maintenance on a code path that has no consumer justification once resources self-manage.

Path C (this decision) is the lowest-magic answer. No new primitive. Just classes with async methods. The user's explicit constraint ("I don't want much magic and stuff") rules.

## Decision 2: Lazy-init resource pattern as the documented idiom

**Decision.** Apps that need async-opened resources hold them as non-Optional fields on AppState. Each resource class encapsulates its own connection state, lazy-init lock, and lifecycle.

```python
class SqliteResource:
    def __init__(self, settings: SqliteSettings) -> None:
        self.settings = settings
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is None:
                self._conn = await aiosqlite.connect(self.settings.path)
            return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> Any:
        return await (await self._ensure()).execute(sql, params)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
```

```python
@dataclass(slots=True)
class AppState:
    settings: AppSettings
    sqlite: SqliteResource          # never None
    browser: BrowserPool            # never None
    llm: Extractor                  # never None


def build_state(settings: AppSettings) -> AppState:    # sync!
    return AppState(
        settings=settings,
        sqlite=SqliteResource(settings.sqlite),
        browser=BrowserPool(settings.browser),
        llm=Extractor(settings.llm),
    )
```

**Rationale.** The lazy-init pattern collapses several pain points at once:

- AppState fields stop being `Optional`. Every consumer-site `if state.sqlite is None: ...` deletes.
- Locks live inside resources, not leaking onto AppState. The `browser_lock` / `llm_lock` fields a2web flagged as smell-y disappear.
- DI is sync. Factory is `build_state: AppSettings → AppState`, plain. No async wrapper. No lifecycle ceremony.
- Cleanup stays explicit via `@on_shutdown` calling `await state.sqlite.close()`. Resource owns its teardown idempotently.

**Cost.** Each resource class grows ~20 LOC (lock, `_ensure`, `close`). For a2web's 3 resources: ~60 LOC growth in resources, offset by ~90 LOC deleted from state.py + server.py shims. Net negative.

**First-call latency.** First tool call that touches sqlite pays the open cost. Subsequent calls don't. Apps that need fail-fast at startup add a `@on_startup` warm-up:

```python
@app.on_startup
async def _warm(state: AppState) -> None:
    await state.sqlite._ensure()   # trigger init
```

This is opt-in. Most apps don't need it.

**Alternative: yield-factories (FastAPI / picodi pattern).** Would let `@app.singleton(AppState)` accept `async def build(...) -> AsyncIterator[AppState]` with cleanup after `yield`. Considered and rejected: requires the container to track yielded async generators across resolution and shutdown, reintroduces lifecycle ownership inside DI, and the magic-level rises again. Lazy-init pays a small per-callsite cost (`await state.sqlite.execute(...)`) to keep the framework dumb.

## Decision 3: Move the container to `packages/di`, drop feature-name awareness

**Decision.** `packages/connections/container.py` → `packages/di/container.py`. The relocated module references no feature names. No `"connection"`. No `_chain_reaches_connection`. No `needs_connection` in any return type.

```
Before                                    After
─────────────────────────────────────     ─────────────────────────────────────
packages/connections/                     packages/di/
  container.py        ~540 LOC              container.py        ~80 LOC
    async resolve                            resolve (sync)
    resolve_sync + SyncResolveUnavailable    __setitem__
    _SingletonWrapper + lock                 __getitem__
    _is_sync_chain, _first_async_dep         has, providers
    _factory_is_async                        partition_kwargs (sync)
    _resolve_factory_kwargs_sync             apply_kwargs (sync)
    _resolve_factory_kwargs (async)
    _chain_reaches_connection
    "connection" magic × 3
                                          packages/connections/
                                            dispatch.py         ~50 LOC
                                              connection load hook
                                            store.py (unchanged)
                                            config.py (unchanged)
                                            "connection" string lives here, only
```

**Rationale.** "We are not a framework, we are a collection of more or less independent libs." That identity requires the substrate (DI) to be importable without importing a feature. Acid test: `a2kit.packages.di` should be useful with no other a2kit package present. Today it isn't — it imports from `a2kit.signature` (fine, that's primitive), but more importantly, *consumers of the container* import from `packages/connections/container.py`, which is the wrong dependency arrow.

**Alternatives considered.**

- *Keep the file in `packages/connections/`, just generalize the magic name into a "wire-scope contributor" protocol.* Considered. Cleaner than today, but it leaves the substrate inside a feature package. The structural signal (where the file lives) matters as much as the code's behavior.
- *Move container to top-level `a2kit/di.py`.* Considered. `packages/di/` chosen for consistency with the rest of the package layout. The top-level `a2kit` namespace stays as a thin re-export surface.

## Decision 4: Connection-string resolution via dispatch hook composition

**Decision.** The connections package owns a dispatch hook that runs before the container's `apply_kwargs`. The hook is async; it awaits `store.load(wire_kwargs["connection"])` and substitutes the resulting `ConnectionConfig` into `wire_kwargs` under whatever parameter name the tool expects. The container then resolves the rest synchronously.

```python
# packages/connections/dispatch.py
def make_connection_hook(container: Container, store: ConnectionStore, config_param: str):
    async def hook(fn, wire_kwargs):
        conn = wire_kwargs.pop("connection", None)
        if conn is not None and _fn_needs(fn, config_param):
            wire_kwargs[config_param] = await store.load(conn)
        return container.apply_kwargs(fn, wire_kwargs)   # sync
    return hook

# Installed during Connections.install(app):
app._dispatch_hook = make_connection_hook(app._container, store, config_param)
```

**Rationale.** The dispatch hook already exists. `app._dispatch_hook` is the seam every transport (MCP, CLI, testing client) funnels through. Today it points at `container_dispatch` (async, container-aware). After this change it points at an async hook that *composes* connection-loading with container resolution. No new abstraction. The "wire transformation" concern moves to where it belongs (the connections package); the "type resolution" concern stays in DI. Each does one thing.

**Multiple hooks?** Out of scope. If a future feature wants to inject before DI (e.g. a tenant resolver), the connections hook composes with it. We do not ship a generic middleware chain primitive until a second use case exists. YAGNI.

## Decision 5: Lifecycle hooks are DI-aware, old signature removed

**Decision.** `@app.on_startup` and `@app.on_shutdown` resolve their kwargs through the dispatch hook (same path tools and health checks use). The `(app: App)` signature is no longer accepted; handlers that need `App` access can request it via the allowlist.

```python
# After
@app.on_startup
async def _warm(state: AppState) -> None:
    await state.sqlite._ensure()
```

**Rationale.** Today's `(app: App)` is the *only* registration point in a2kit that doesn't go through DI. The asymmetry is the source of a2web Gap 2. Routing lifecycle through the dispatch hook collapses the asymmetry to zero. Health does it already (`packages/health/__init__.py:97-109`); the same model applies.

**Breaking the old signature** is deliberate. The migration is one-liner per hook; the long-term gain is one DI model across all registration points.

**Alternatives considered.**

- *Signature-shape detection (resolve `(state: AppState)`, fall back for `(app: App)`).* Considered for back-compat. Rejected because (a) no deprecation is the project decision and (b) signature-shape detection is a kind of magic the project is explicitly cutting.

## Decision 6: `App.container()` returns non-Optional

**Decision.** The container is eager-initialized in `App.__init__`. `App.container()` returns `Container`, not `Container | None`. The `_ensure_container` lazy path is removed.

**Rationale.** The Optional return type forces dead defensive code at every consumer site (`if container is None: raise RuntimeError`). The "lazy until first `provide`/`singleton`" optimization saves zero meaningful cost (Container is ~80 LOC after the strip-down). Eager-init is simpler, and the type narrows.

## Decision 7: Unify dispatch entry points

**Decision.** `health.run_checks` (and the test client's `_invoke_through_dispatcher`) call `container.apply_kwargs(fn, wire)` directly, not `app._dispatch_hook(fn, wire)`. The dispatch hook stays the per-call seam; `apply_kwargs` is the DI seam. Health checks and lifecycle hooks don't go through the dispatch hook because they are not tool calls; they go through DI directly.

**Rationale.** Cleaner separation. The dispatch hook composes wire-transformation (e.g., connection load) with DI; health/lifecycle don't have wire kwargs. One seam per concern.

## Open question (decided, recording for future-self)

**Should we ship a `LazyResource` base class in a2kit core?** Decided: no. Each resource is ~20 LOC of trivial scaffold. Bundling a base class makes a2kit own a pattern that's not specific to it. Resource classes are the consumer's concern. If a2kit ever ships its own resources (e.g. an `a2kit.sqlite` package), it can use the pattern internally without externalizing it.

## Migration outline (for a2web)

Reference for the consumer, captured here so the proposal isn't the source of truth for migration steps.

1. Make `AppState` fields non-Optional. Remove `*_lock` fields.
2. Add lazy-init scaffolding to `SqliteResource`, `BrowserPool`, `Extractor` (each gains `_lock`, `_ensure`/equivalent, `close`).
3. Change `build_state` from async to sync.
4. Change `app.singleton(AppState, factory=build_state)` invocation — no API change, just the factory is now sync.
5. Rewrite `_open_resources` / `_close_resources` lifecycle hooks to take `state: AppState` directly; drop the `_app.container()` dance.
6. Optional: add a `@on_startup` warm-up hook if fail-fast matters.

Estimated effort: half a day in a2web.
