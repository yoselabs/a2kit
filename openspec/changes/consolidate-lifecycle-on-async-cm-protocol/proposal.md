# Consolidate lifecycle on Python's async-context-manager protocol

## Why

a2kit's current lifecycle surface has three primitives that overlap:

| primitive                                  | role                                          |
|--------------------------------------------|-----------------------------------------------|
| `App(..., lifespan=cm)`                    | imperative startup/shutdown bookends         |
| `Router.lifespan` classmethod              | router-scoped CM, composed into App lifespan |
| `app.singleton(T, fn, teardown=)`          | resource ownership with declarative cleanup  |

For the common "open resource X, close resource X" case all three can
express the same thing. The split was historically deliberate
(`2026-05-13-lifespan-over-lifecycle-hooks` chose `lifespan=` to align
with FastMCP's primitive; `2026-05-12-singleton-async-factories` chose
`singleton(T, fn)` over `@app.async_resource`; `2026-05-13-singleton-
teardown-topological` added `teardown=` to stop hand-rolled finally
chains). The cost has accumulated: docs have to explain "which one
to use," each consumer hand-picks differently, the framework carries
three wiring paths into one FastMCP `lifespan(server)` slot.

CLAUDE.md's "no redundancy / no multiple ways" rule bites. The
unifier already exists in Python: `__aenter__` / `__aexit__`. Every
lifetime-bearing object the framework cares about — DB pool,
HTTP client, browser handle, LLM client, router — can declare its
lifecycle via the standard protocol. The framework's job collapses
to "compose them in the right order."

## What Changes

### Singletons: type-inferred registration, auto-detected lifecycle

```python
# before
async def _open() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30)
app.singleton(httpx.AsyncClient, _open, teardown=lambda c: c.aclose())

# after — type inferred, lifecycle auto-detected from __aenter__/__aexit__
app.singleton(lambda: httpx.AsyncClient(timeout=30))
# or for a zero-arg ctor:
app.singleton(httpx.AsyncClient)
```

- **MODIFY** `app.singleton(...)`: accept either a class (no factory needed) or
  a factory (annotated return type carries the registration type). Drop the
  explicit `T` positional in both cases. Raise `TypeError` if the factory's
  return type can't be resolved.
- **REMOVE** `teardown=` kwarg. The framework probes the resolved instance
  for `__aexit__` / `aclose` / `close` in that order and wires whichever it
  finds into the unwind stack.
- **REMOVE** `eager=` (never shipped) — singletons enter eagerly during
  App `__aenter__`. Lazy singletons are not part of this surface.
- Singletons enter in **topological order** (dependencies first) during
  App `__aenter__`; unwind in **reverse topological order** during App
  `__aexit__`. Topology is derived from the existing DI graph
  (per `singleton-teardown-topological`).

### Routers: `__aenter__`/`__aexit__` instead of `lifespan` classmethod

```python
# before
class Github(a2kit.Router):
    slug = "gh"
    tools = (...)
    @asynccontextmanager
    async def lifespan(self):
        self.client = httpx.AsyncClient()
        try:
            yield
        finally:
            await self.client.aclose()

# after
class Github(a2kit.Router):
    slug = "gh"
    tools = (...)
    async def __aenter__(self):
        self.client = httpx.AsyncClient()
        return self
    async def __aexit__(self, *_):
        await self.client.aclose()
```

- **MODIFY** `Router`: subclasses opt into lifecycle by implementing the
  async-CM protocol on the instance. The base class declares no
  `lifespan` method.
- **REMOVE** `Router.lifespan` classmethod surface. `add_router` checks for
  `__aenter__` on the instance instead.
- Routers enter **lazily** on first dispatch of any tool belonging to that
  router. Routers never used during a session never enter their `__aenter__`.
  Once entered, routers stay entered until App `__aexit__`.
- Router unwind happens during App `__aexit__` in reverse-of-enter order
  (LIFO).

### App: drop `lifespan=` constructor argument

- **REMOVE** `lifespan: Callable | None` from `App.__init__`. Passing
  `lifespan=` raises `TypeError` with hint pointing at the singleton /
  Router `__aenter__` migration paths.
- **REMOVE** `a2kit.lifespan.compose`. Composition is internal to the
  framework via `AsyncExitStack`.
- **REMOVE** the `a2kit.lifespan` public module. The `HasLifespan` Protocol
  drafted earlier is unnecessary.
- App becomes its own async context manager:
  `async with app:` enters all singletons in topological order; exits
  unwind in LIFO order. Construction (`a2kit.App(...)` + `add_router(...)`)
  remains pure — no async work, no resource enter. **Use this property
  for unit tests that only check wiring** (no async needed; nothing
  fires).

### Pure-imperative bookends ("warm cache, no resource")

Live in `main()` before `async with app:`. Not a framework concern.

If the consumer wants the work composed into the lifespan unwind for some
reason, they wrap as a marker singleton:

```python
class _Warmup:
    async def __aenter__(self): await prewarm(); return self
    async def __aexit__(self, *_): pass

app.singleton(_Warmup)
```

Eager singleton entry guarantees it fires at App `__aenter__` time.
This is the documented escape hatch; there is no `app.use(cm)` API.

### FastMCP / CLI / test transport wiring

- `build_mcp_server(app)` adapts a2kit's `async with app:` into FastMCP's
  `lifespan(server)` slot via a thin adapter that calls
  `app.__aenter__()` / `app.__aexit__()`.
- `cli.runtime` does the same: dispatches inside `async with app:`.
- `TestClient(app)` becomes `async with TestClient(app) as client:` —
  enters the App, dispatches, unwinds on exit. The `async with` shape
  is already idiomatic for the in-process test client.

### Type inference rules (detail)

```
factory shape                                   inferred type
─────────────────────────────────────────────   ────────────────────────────
app.singleton(SomeClass)                        SomeClass
app.singleton(lambda: SomeClass(...))           SomeClass (from lambda
                                                annotation if present,
                                                else from the constructed
                                                instance class — see below)
app.singleton(factory)  where factory has       factory's return type
   `-> T` annotation
app.singleton(factory)  where factory has       TypeError at registration:
   no return annotation                         "factory must have a return
                                                 type annotation or pass a
                                                 class directly"
```

For the lambda case (no annotation, no class), the framework can either:
(a) inspect the lambda's first call result and register under
`type(result)`, or
(b) raise `TypeError` and require either `lambda: SomeClass(...)` typed
or a top-level `def factory() -> T:`.

**Pick (b)** — explicit, no first-call-time surprises. The lambda
ergonomic case is `app.singleton(SomeClass)` (zero-arg ctor) or
`app.singleton(lambda: SomeClass(a, b))` becomes
`app.singleton(_make_some_class)` with a top-level annotated function
when args are needed.

Actually that's friction. Reconsider (a): allow lambda without
annotation, register under `type(instance_returned)`. Catch the rare
ambiguity (subclass returned, want base type) by passing the class
explicitly:

```python
app.singleton(BaseClass, lambda: SubClass())   # explicit base registration
```

**Decision: support both shapes — `app.singleton(factory)` infers, with
optional first positional `app.singleton(T, factory)` for explicit
override.** Documented in design.md.

## Capabilities

### Modified Capabilities

- `app-lifecycle`: removes `lifespan=` argument; introduces `async with app:`
  as the canonical entry; routers and singletons compose via
  `AsyncExitStack`; topological-order singleton entry replaces
  ad-hoc startup logic.
- `app-singletons`: registration becomes type-inferred (or class-as-factory);
  `teardown=` and `eager=` kwargs removed; lifecycle is auto-detected from
  the resolved instance's protocol; topological enter and reverse-topological
  exit are framework guarantees.
- `router-conventions`: lifecycle moves from `Router.lifespan` classmethod
  to instance `__aenter__`/`__aexit__`; routers enter lazily on first
  dispatch of a tool belonging to them.

## Risk

High-blast-radius breaking change. Every consumer using `lifespan=`,
`Router.lifespan`, or `app.singleton(T, fn, teardown=)` migrates.

Mitigations:
- Hard crash on each removed surface with embedded migration hint, per
  CLAUDE.md "no backward compat shims."
- Migration table in CHANGELOG with side-by-side before/after for each
  shape.
- a2web's lifespan body is the canonical migration target — port it as
  part of this change to validate the new shape.

## Why one proposal instead of three

The three primitives (`lifespan=`, `singleton(teardown=)`,
`Router.lifespan`) are interlocking — removing one in isolation leaves
the others incoherent. The migration table and the AsyncExitStack
composition only make sense end-to-end. Splitting the change creates a
multi-step "during the migration period" state where consumers can't
write a coherent app.

## Replaces in-flight work

This change supersedes the `HasLifespan` Protocol addition that was
mid-flight in `refine-core-clean-and-router-types` task 4. The
`HasLifespan` type becomes dead code under this model and was reverted
before this proposal landed.

## Out-of-scope

- Per-request resource scopes beyond the existing `app.provide(factory)`
  request-scoped DI. That stays as-is.
- Idle-timeout-driven router teardown / re-entry. Routers stay entered
  for the lifetime of the App once first touched.
- Health-probe integration. The "is the app healthy?" question is
  orthogonal — covered by the separate `remove-health-tool-flag`
  proposal.
