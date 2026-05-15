## Why

`a2kit.testing.peek(app, T)` exposes a sync test seam for reading
already-cached app-scope singletons. It does not run the dependency
chain — it only reads `_singletons`.

a2web (round-10 Friction A3) hand-rolls
`make_default_state(settings=...)` in `tests/conftest.py` that
manually wires `breakers`, `proxy_pool`, `sqlite` to build an
`AppState`. The reason that helper exists: there's no public async
seam to say "give me the resolved DI instance for T as the
dispatcher would inject it."

The framework already exposes this via `await
app.container().get(T)` (documented in the
`in-process-test-client` capability), but the call site is verbose
and the seam isn't named. `a2kit.testing.resolve(app, T)` is the
async sibling of `peek` — three lines wrapping
`container.get(T)`, matching the existing helper-naming pattern.

I initially parked this on the "needs scope CM design" concern.
On second look: there's no leaked-resource scenario. Resources
resolved via `Container.get` go on the appropriate cleanup stack
(root for SINGLETON, child for SCOPED). For tests using
`async with a2kit.testing.client(app)` or `async with app:`, the
lifespan close drains the root stack normally. `resolve` is a
read-only seam over the existing async resolution path.

## What Changes

### `a2kit.testing.resolve(app, type_)`

Async helper:

```python
async def resolve(app_: App, type_: type) -> Any:
    return await app_.container().get(type_)
```

Added to `src/a2kit/packages/testing/__init__.py` alongside
`peek`. Re-exported through `src/a2kit/testing.py`.

The function SHALL run the full DI resolution chain — building T
if not cached, entering `__aenter__` for resources, recording
cleanup on the appropriate scope's stack. This is the same path
that tool dispatch follows for injected kwargs.

Callers SHALL invoke this inside an entered app context
(`async with a2kit.testing.client(app):` or `async with app:`) so
the cleanup stack is alive to receive recorded `__aexit__`
callbacks. Calling outside an entered app leaves resources
half-entered with no scope to exit them; this matches today's
behaviour of `await app.container().get(T)` directly.

### Why a separate function name (and not just document `container().get`)

Three reasons:

1. **Pattern parity with `peek`.** Tests reading sync state use
   `peek(app, T)`; tests resolving async deps now have
   `resolve(app, T)`. Sibling functions, consistent shape.
2. **Naming intent.** `container().get(T)` is internal-flavoured
   ("reach into the container"); `testing.resolve(app, T)` is
   intent-flavoured ("get me the resolved value").
3. **Discoverability.** `a2kit.testing.*` is the indexed surface
   tests find via autocomplete; `app.container().get` is a chain
   most consumers wouldn't think to traverse.

## Out of scope

- Scope context manager (`resolution_scope`) — not needed. The
  existing `async with app:` / `async with client(app):` patterns
  provide the scope; `resolve` reads through that scope.
- Sync version — `peek` already covers the sync case for cached
  singletons.
- Bypass for testing — `resolve` runs the same path as production
  dispatch; tests that need different behaviour use
  `app.provide(T, fake_factory)` to override at composition root.

## Impact

- **Surface**: one new symbol on `a2kit.testing.*`. No new
  top-level `a2kit.*` surface.
- **Spec**: `in-process-test-client` capability gains one
  requirement.
- **Tests**: 3 BDD scenarios — resolves an app-scope singleton,
  enters `__aenter__` on first call, returns cached instance on
  second call.
- **Consumer migration**: a2web's `make_default_state` collapses
  to `state = await a2kit.testing.resolve(app, AppState)` (after
  they migrate their state setup to a single factory under
  `app.provide(AppState, make_state)` — which they can pair with
  the now-shipped `lazy-in-factory-params` change).
