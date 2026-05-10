## Context

a2kit today exposes one composition primitive (`App.provide`) and one runner entry (`a2kit.run(app)`). Resource lifecycle is missing from both transports:

- **CLI path**: `run(app)` calls `build_full_cli(app).main(...)` synchronously. Each Click subcommand internally calls `asyncio.run(...)` for its async tool body. There is no place a user can hook "open the sqlite connection once before the command runs, close it after".
- **MCP path**: `build_mcp_server(app, **fastmcp_kwargs)` already forwards `lifespan=` straight to FastMCP. A user *could* construct an async context manager and pass it through, but the App has no API to register handlers, and the same handlers cannot be reused on the CLI path.

The DI container (`packages/connections/container.py`) is request-scoped: every dispatch builds fresh instances. App-scoped state has to be smuggled through `provide(T, lambda: closed_over_state)` closures. Two-App test isolation is preserved only because users avoid `lru_cache`; the convention is fragile and unenforced.

`Container.resolve` is `async`-only and requires a `connection` kwarg, even when no connection plugin is installed. Tests that want to peek at App-scoped state have no synchronous path; connection-less apps type `connection=None` everywhere.

The downstream effect (a2web's `state.py` carries the canonical example): a custom `register_state(app)` closure, three `ensure_X` lock-guarded lazy initializers, an `atexit` handler that opens a fresh event loop to close async resources, and a defensive comment explaining why `lru_cache` would be wrong. ~80 LOC of boilerplate that exists because a2kit lacks small primitives.

## Goals / Non-Goals

**Goals:**
- One lifecycle API that works identically on CLI and MCP.
- App-scoped singletons that survive across a process / a lifespan but not across two `App` instances in the same process.
- Sync resolve for tests and stub paths.
- Default `connection=None` so connection-less apps stop typing dead syntax.
- Zero new dependencies.
- No regression to the bare-`import a2kit` cold-start invariant.

**Non-Goals:**
- Per-request scoped resources (request-scoped DI already covers this).
- Process-wide singletons (intentionally unsupported — would break two-App test isolation).
- Lifespan hooks running in parallel (sequential is enough; consumers can fan out inside a single handler if they want).
- Restart / hot-reload of singletons.
- Generic priority/ordering knobs for handlers — registration order only.

## Decisions

### 1. Lifecycle handlers are stored on the App, dispatched by both transports

`App._startup_handlers: list[Callable[[App], Awaitable[None]]]` and `_shutdown_handlers: list[...]`. `App.on_startup(fn)` and `App.on_shutdown(fn)` accept either a plain callable (returns the callable, so it works as a decorator) or are themselves used decorator-style. Handlers receive the `App` so they can access `app.singleton(...)`-resolved state, settings, etc.

**MCP path** — `build_mcp_server` derives a `lifespan` async context manager from the App's handlers and merges it with any user-supplied `lifespan=` kwarg. Merge semantics: a2kit's startup handlers run *before* the user's lifespan body; a2kit's shutdown handlers run *after* the user's body unwinds. If the user passed `lifespan=fn` and we have handlers, both run; if the user passed `lifespan=` and we have no handlers, nothing changes; if we have handlers and the user passed nothing, we install ours.

**CLI path** — `run(app)` wraps `build_full_cli(app).main(...)` in a one-shot async lifespan. Concretely, `run()` becomes: build the CLI, attach a Click `result_callback` (or wrap `cli.main` in a try/finally) that runs startup before the subcommand's `asyncio.run(...)` and shutdown after. Because each Click subcommand spins its own event loop, lifecycle dispatch acquires its own loop via `asyncio.run(_lifespan_runner(app, cli, argv))` — the runner becomes one async function that calls startup, awaits the command body (synchronously dispatched via Click but the body itself is async), then shutdown.

The handler order: startup runs in registration order; shutdown runs in *reverse* registration order (LIFO unwind, like a stack of context managers). This matches user intuition from contextlib.

**Failure semantics:**
- Startup raises → no later startup handlers run, no shutdown handlers run, exception propagates to the caller of `run()` (CLI exits nonzero) or to FastMCP (which aborts the connection). Rationale: if `open_sqlite` raised, there is nothing to close.
- Shutdown raises → log via `logging.getLogger("a2kit.lifecycle")` at ERROR level with traceback, continue running remaining handlers, swallow. Rationale: the process is going away regardless; a shutdown error must not mask the actual exit reason.

**Alternatives considered:**
- *contextlib.AsyncExitStack* — natural fit for "stack of context managers", but forces users to write `@asynccontextmanager` for trivial open/close pairs. The on_startup/on_shutdown split is more familiar (FastAPI, Starlette).
- *Single `lifespan` decorator that yields* — same nesting cost. Rejected for the same reason. (We could add this later as sugar; for v1 we ship the two-decorator form which is what a2web's feedback explicitly asks for.)

### 2. `App.singleton(T, factory=None)` is a thin cap on `provide`

Implementation: `singleton` registers a wrapper provider that calls the user's factory at most once per App, caching the result on the App instance (`App._singletons: dict[type, Any]`). The wrapper is a normal provider, so resolution chains, container caching, and the `connection`-aware machinery all work unchanged.

```python
def singleton(self, type_, factory=None):
    if factory is None:
        return lambda fn: self.singleton(type_, fn)  # decorator form
    sentinel = object()
    self._singletons[type_] = sentinel
    def _cached(*args, **kwargs):
        cached = self._singletons[type_]
        if cached is sentinel:
            cached = factory(*args, **kwargs)
            self._singletons[type_] = cached
        return cached
    self.provide(type_, _cached)
    return self
```

Two App instances → two `_singletons` dicts → two cached values, naturally. The two-App canary test in a2web becomes redundant.

`has_singleton(T)` returns `True` if the type is in `_singletons` (regardless of whether it's been resolved yet). `singletons()` returns a snapshot dict for diagnostics.

**Async factories:** if the user-supplied factory is `async`, `singleton` registers an async wrapper that awaits the factory under an `asyncio.Lock` (created lazily on first resolve). Subsequent calls return the cached value without acquiring the lock. This handles the lazy-init case for resources that need an event loop to construct, without exposing locks in user code.

**Alternatives considered:**
- *Process-wide cache via `lru_cache`* — explicitly rejected; breaks two-App isolation. The whole point of this primitive is to provide the safe shape.
- *Make `provide()` itself cache* — would break per-dispatch resolution semantics for users who depend on it. Keep `provide` per-dispatch, add `singleton` as the cached cap.

### 3. `Container.resolve_sync(T)` walks the chain synchronously, raises if any link is async

The async `resolve` already inspects each factory's parameters and recursively resolves them; the sync variant does the same but rejects async factories upfront. Implementation: a helper `_is_sync_chain(type_)` walks the provider graph reachable from `type_`, checking `inspect.iscoroutinefunction` on each factory. If any is async, `resolve_sync` raises `SyncResolveUnavailable(type_, async_link=T2)` with the offending link named.

Rationale for naming: the offending link is the actionable information — tests can either swap that provider or use the async path.

**`connection=None` default**: trivial — change `def resolve(self, type_, *, connection)` to `def resolve(self, type_, *, connection=None)`. No call site changes; absent connection plugin, the value was `None` anyway. `resolve_sync` adopts the same default.

### 4. Documentation: the `provide` vs `singleton` decision tree

Most a2kit consumers will reach for `singleton` for app-state (sqlite, settings, breakers) and `provide` for per-dispatch resources (per-connection clients). The README + a CLAUDE.md section will spell out the rule:

- Lifetime longer than one tool call → `singleton`.
- Built fresh per dispatch (especially: depends on `connection: str`) → `provide`.

This is mostly capturing what a2web learned the hard way.

## Risks / Trade-offs

- [**Risk**] Users register a synchronous startup handler that does blocking I/O on the event loop thread → blocks server startup. **Mitigation**: handlers are typed `Callable[[App], Awaitable[None]]`; we accept sync callables but document the async preference. The lint rule that flags blocking calls in async functions (existing `ASYNC100/210/230`) covers tools but not lifecycle handlers; we extend its scope or add a small new rule in a follow-up — out of scope here.
- [**Risk**] User passes `lifespan=...` to `build_mcp_server` AND registers `on_startup` handlers, expecting parallel/independent semantics. **Mitigation**: the merge order (a2kit-startup → user-lifespan → user-body → user-shutdown → a2kit-shutdown) is documented. If users dislike it, they can call `app.on_startup` from inside their lifespan instead.
- [**Risk**] `singleton` factories that take `connection: str` (a connection-bound dep) silently hide multi-connection bugs because the cached instance is bound to the first connection seen. **Mitigation**: at registration, walk the factory signature; if any param resolves to `connection: str` (or any connection-config type), raise `ValueError("singleton factories cannot depend on connection; use provide() instead")`. This is the highest-likelihood footgun and the cheapest to prevent.
- [**Trade-off**] `resolve_sync` cannot resolve async factories at all — even if the test only needs the sync prefix of the chain. We considered allowing partial resolution (sync until you hit async, then raise), but it confuses the test ergonomics story. Keep it strict: either the whole chain is sync or you use the async path.
- [**Trade-off**] We don't add `App.on_request_start` / `on_request_end` (per-tool-dispatch hooks). Those have legitimate use cases (telemetry, audit) but the request-scoped DI container already handles per-dispatch resources, and dispatch hooks deserve their own design pass.
- [**Risk**] Shipping `singleton` may tempt users to put everything in singletons and skip per-dispatch DI, leading to hidden global state. **Mitigation**: the "singleton vs provide" docs section explicitly steers people away from this; lint can grow a rule later if abuse becomes a pattern.

## Migration Plan

This is additive — no migration needed for existing apps. a2web (and any other consumer) opts in by:

1. Replacing `register_state(app, settings=...)` with `app.singleton(AppState, lambda: AppState(...))`.
2. Replacing `_atexit_close` and `ensure_X` lock dances with `@app.on_startup` / `@app.on_shutdown` handlers that open/close resources directly.
3. Replacing `await container.resolve(T, connection=None)` in tests with `container.resolve_sync(T)` where the chain is sync, or `await container.resolve(T)` if they prefer async.

Rollback: each primitive can be removed independently; nothing in the existing surface depends on these being present.

## Resolved Decisions

- **Handler signature is `(app)` only.** Handlers run before any tool dispatch; there is no per-request context to surface. FastMCP's per-server lifespan context is reachable by users who pass their own `lifespan=` kwarg to `build_mcp_server` alongside App handlers — the merge order documented in §1 makes them compose. Coupling our signature to FastMCP internals would diverge CLI vs MCP and add a Union type for nothing.
- **`singleton`, `on_startup`, `on_shutdown` accept both method and decorator form.** Disambiguation is a single `if factory is None` (or `if fn is None`) check. Cost is trivial; ergonomic win is real (decorator form is what a2web's feedback explicitly asks for).
