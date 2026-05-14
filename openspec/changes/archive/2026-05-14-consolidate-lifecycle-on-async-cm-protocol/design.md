# Design — consolidate lifecycle on async-CM protocol

## Decisions

### D1. App is an async context manager

`a2kit.App` implements `__aenter__` and `__aexit__` directly:

```python
class App:
    async def __aenter__(self) -> App:
        async with AsyncExitStack() as stack:
            # 1. Topologically order singletons by DI graph.
            for t in self._container.singleton_order():
                instance = await self._container.aresolve(t)
                if hasattr(instance, "__aexit__"):
                    await stack.enter_async_context(instance)
                elif hasattr(instance, "aclose"):
                    stack.push_async_callback(instance.aclose)
                elif hasattr(instance, "close"):
                    stack.callback(instance.close)
            self._stack = stack.pop_all()
        self._entered_routers: dict[str, Router] = {}
        return self

    async def __aexit__(self, *exc) -> None:
        # routers entered lazily during dispatch; LIFO unwind first
        for r in reversed(list(self._entered_routers.values())):
            if hasattr(r, "__aexit__"):
                await r.__aexit__(*exc)
        await self._stack.__aexit__(*exc)
```

**Rationale**: standard Python protocol; supports `async with app:`
idiom; composition is `AsyncExitStack` (well-understood); tests can
introspect `app` without entering.

### D2. Routers enter lazily on first tool dispatch

Dispatcher pseudocode:

```python
async def _dispatch(self, tool_name: str, **kwargs):
    router_slug, tool = self._resolve(tool_name)
    if router_slug not in app._entered_routers:
        router = self._routers[router_slug]
        if hasattr(router, "__aenter__"):
            await router.__aenter__()
        app._entered_routers[router_slug] = router
    return await tool(**kwargs)
```

**Rationale**: Routers should not impose startup cost for tools the
session never touches. Routers may carry router-scoped resources (auth
tokens, session handles) that shouldn't exist if the router is unused.

**Concurrency**: per-router `asyncio.Lock` guards first-touch
coalescing. N concurrent dispatches to the same router share one
`__aenter__` invocation; the first awaiter's exception (if any)
propagates to all.

**Failure mode**: If `Router.__aenter__` raises, the router is **not**
recorded in `_entered_routers` — next dispatch retries. This matches
async-singleton first-touch semantics from `singleton-async-factories`.

### D3. Type inference for `app.singleton(...)`

Three shapes accepted:

```python
# 1. class as factory (zero-arg ctor):
app.singleton(SomeClass)

# 2. factory with return annotation:
async def _make() -> SomeClass: ...
app.singleton(_make)

# 3. explicit override (subclass returned, want base registration):
app.singleton(BaseClass, lambda: SubClass())
```

**Resolution algorithm**:

```python
def singleton(arg1, arg2=None):
    if arg2 is None:
        # one-arg form
        if inspect.isclass(arg1):
            T, factory = arg1, arg1
        else:
            T = _return_type_of(arg1)
            if T is None:
                raise TypeError(
                    "app.singleton(factory) requires a return annotation. "
                    "Either annotate the factory ('-> T') or pass the type "
                    "explicitly: app.singleton(T, factory)."
                )
            factory = arg1
    else:
        T, factory = arg1, arg2
    self._container.register_singleton(T, factory)
```

**Lambda without annotation** raises at registration, not first-call.
The error names the affected call site and suggests both fixes.

### D4. Remove `a2kit.lifespan` public module

The module currently exports `compose(...)` and (proposed) `HasLifespan`.
Under this design:
- `compose(...)` is dead — composition is internal `AsyncExitStack`.
- `HasLifespan` is dead — the protocol is `__aenter__`/`__aexit__`.

The module deletes. Imports of `from a2kit.lifespan import compose`
raise `ImportError` at module-load time (Python's natural failure
mode for removed modules). The error message lives in CHANGELOG's
migration table; we don't ship a shim.

### D5. FastMCP wiring

Today `build_mcp_server(app)` constructs a FastMCP server with
`lifespan=app.lifespan_cm()`. Under this design:

```python
def build_mcp_server(app):
    @asynccontextmanager
    async def _adapter(server):
        async with app:
            yield
    return FastMCP(name=app.name, lifespan=_adapter, ...)
```

The adapter is the only place `__aenter__`/`__aexit__` get wrapped
into FastMCP's CM-shaped slot. Internal-only — not a public surface.

### D6. CLI wiring

Today the CLI dispatcher constructs a per-invocation lifespan:

```python
async def _run(args):
    async with app.lifespan_cm():
        return await dispatch(...)
```

After:

```python
async def _run(args):
    async with app:
        return await dispatch(...)
```

Same wrapper — different inner surface.

### D7. TestClient wiring

Today `TestClient(app)` is sync-constructed and enters the lifespan
during `__aenter__`. After:

```python
async with TestClient(app) as client:
    await client.invoke("gh.fetch", id=1)
```

Internally `TestClient.__aenter__` calls `await app.__aenter__()` then
opens a `fastmcp.Client(transport=build_mcp_server(app))`. Routers stay
lazy — they don't enter until `client.invoke` actually dispatches.

### D8. Migration error messages

Each removed surface raises with a specific hint. Sample shapes:

```python
# App(..., lifespan=...)
raise TypeError(
    "App(lifespan=...) was removed in v0.35. "
    "Express imperative bookends as a marker singleton "
    "(`class _Warmup: __aenter__/__aexit__`; "
    "`app.singleton(_Warmup)`) or move the work into main() "
    "before `async with app:`."
)

# app.singleton(T, factory, teardown=fn)
raise TypeError(
    "app.singleton(..., teardown=...) was removed in v0.35. "
    "Move cleanup onto the resource itself via __aexit__, "
    "aclose, or close — the framework auto-detects it."
)

# Router.lifespan classmethod
# raised by add_router when it detects `lifespan` in cls.__dict__:
raise TypeError(
    f"Router subclass {cls.__name__!r}: `lifespan` classmethod "
    "was removed in v0.35. Implement `__aenter__` and `__aexit__` "
    "on the Router instance instead."
)
```

### D9. App construction stays pure

No `__aenter__` work during `a2kit.App(...)` or `app.add_router(...)`.
The DI container can be inspected, singletons enumerated, routers
introspected — all without firing a single `__aenter__`. This is the
testing escape hatch for "wire-up tests" that don't need full
lifecycle.

```python
def test_wiring():
    app = build_app()
    assert {r.slug for r in app.routers} == {"gh", "slack"}
    # zero async, zero __aenter__ calls
```

### D10. Topological order derivation

Reuse the existing `Container._collect_reachable` helper from
`singleton-teardown-topological`. Walk the DI graph from each
registered singleton; the topological order is well-defined for any
acyclic DI graph (which the framework already validates at
`add_router` time).

Cycles in the DI graph raise at registration today; this design does
not change that contract.

## Rejected alternatives

### R1. Keep `lifespan=` for "imperative bookend" cases

Considered: keep `App(..., lifespan=cm)` for warm-cache / metrics-flush
cases.

Rejected: redundant with marker-singleton pattern; users would have
two competing idioms ("when do I use lifespan= vs a marker
singleton?"). The marker-singleton pattern is a small footnote in the
docs; `lifespan=` is a full constructor argument that consumers default
to. Forcing the issue into singletons unifies the mental model.

### R2. Add `@app.resource` decorator with yield

Considered: `@app.resource async def db() -> AsyncIterator[DB]: ...`
shape (FastAPI Depends-with-yield).

Rejected: the explicit prior decision in
`2026-05-12-singleton-async-factories` was no new decorator. The
class-with-`__aexit__` shape uses Python's actual protocol; the
decorator shape invents a new one. Singletons already accept
`async def` factories from that prior change; the protocol detection
on the returned instance is the smaller surface delta.

### R3. `app.use(cm)` for compose-extra-CMs

Considered: explicit registration of additional CMs into the lifespan
stack.

Rejected: every legitimate use-case for `app.use(cm)` either has a
natural resource owner (becomes a singleton) or is genuinely imperative
startup work with no resource (lives in `main()`). The `use(cm)`
surface invites consumers to bypass the type system by registering
anonymous CMs that hide what they own.

### R4. Eager router entry at App `__aenter__`

Considered: enter all routers at App startup, alongside singletons.

Rejected: defeats the testing-and-development use case where you spin
up an app to dispatch one tool. Also: routers carry router-scoped
resources (HTTP sessions, auth tokens) that shouldn't exist if the
router isn't used. Lazy router entry is the user's explicit
preference and matches the design intent of routers as "groups of
tools sharing dependencies."

### R5. `eager=True` kwarg on singleton

Considered: opt-in eager singleton entry.

Rejected: with topological ordering and shared-resource semantics,
ALL singletons should enter eagerly — that's the contract of "shared
resource." A lazy singleton is conceptually a request-scoped provider
(`app.provide(...)`). The `eager=` kwarg invites a confusing third
state.

## Open questions (defer to implementation)

- **Q1**: Does dispatching a `tool` that doesn't belong to any router
  (i.e. registered directly on the App) skip router-enter entirely?
  Answer: yes — only tools-via-routers trigger router `__aenter__`.
  Direct app-tools are dispatched immediately after singletons are in.
  *(Confirmed during proposal review.)*

- **Q2**: If `Router.__aenter__` raises during first dispatch, does
  the in-flight request fail with the original exception or a wrapper?
  Answer: original exception propagates through the MCP error envelope
  (per `mcp-context-passthrough`). The dispatcher does not catch.
  *(Confirmed during proposal review.)*

- **Q3**: Order between singletons entering and lifespan-composed FastMCP
  middleware entering? Answer: a2kit owns the singleton stack inside
  the FastMCP `lifespan(server)` body — singletons enter inside FastMCP
  startup, after FastMCP's own middleware init. Standard order.
