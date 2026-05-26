## Design notes — generalise context bridges

### Why act now (BACKLOG said "at N=2")

The BACKLOG entry sized the trigger as "first proposal that would
otherwise add a second `_<x>_bridge.py`." The 2026-05-26 audit shows N
is already 3 (Principal, request_scope, LDD) and 4 if you count the
MCP `_pending_typed_envelope` middleware bridge. The audit found this
by looking — the bridges weren't proposed as `_<x>_bridge.py` because
they predate the principal one and use slightly different naming
conventions. The semantic count is what matters; the trigger condition
is met.

### Why keep them named-but-shim instead of deleting

`set_request_principal` / `current_request_principal_seeds` /
`reset_request_principal` only just landed via
`consolidate-principal-bridge`. Substrate writers across `auth/`,
`mcp/`, `http/` import them. Deleting the names in the same release
is unnecessary churn; one-release shim keeps the migration cost low
for both this repo's tests and any out-of-tree consumer.

The shim is small (3 functions, ~12 LOC, each routes to a single
`request_scope` call) and the deletion is BACKLOG-tracked.

### Where to put `request_scope.py`

Two candidate sites:

```
packages/dispatch/request_scope.py     ← dispatch layer (L4)
packages/context/request_scope.py      ← context layer (L0/L1)
```

**Recommendation: `packages/dispatch/request_scope.py`.** Reasoning:

- It's a substrate↔dispatch bridge. Substrate writers already import
  dispatch for `install_substrate_signature`. Readers are dispatch
  stages. No new layer crossings.
- `packages/context/` carries pure types (`ToolContext` protocol,
  Principal). Adding a stateful bridge there muddles that layer.
- Mirrors the precedent of `_principal_bridge.py` being in dispatch.

If the layer DAG turns out to forbid this once Tach lands
(`adopt-arch-fitness-functions`), move to `packages/context/` with a
documented exception — but probe it first.

### The `RequestScope` shape

```python
# packages/dispatch/request_scope.py

T = TypeVar("T")
ScopeToken = Token  # alias for contextvars.Token, opaque to callers

class RequestScopeMissing(LookupError):
    def __init__(self, t: type[Any]) -> None:
        super().__init__(
            f"RequestScope has no value of type {t.__name__!r}. "
            f"Substrate middleware did not publish() it; check the "
            f"middleware order at the transport boundary."
        )
        self.requested_type = t

def publish(*values: object) -> ScopeToken:
    """Publish typed seeds for the current request scope.

    Returns a single token that reset() will use to clear ALL of them
    atomically. Multiple values may share types; the last-published
    wins (matches Container.provide semantics).
    """
    ...

def get(t: type[T]) -> T:
    """Read a typed seed; raise RequestScopeMissing(t) if absent."""
    ...

def try_get(t: type[T]) -> T | None:
    """Read a typed seed or None."""
    ...

def all_seeds() -> dict[type, object]:
    """For Container.call_scope integration. Returns a copy."""
    ...

def reset(token: ScopeToken) -> None:
    """Reset every value the publish() that returned this token added."""
    ...
```

### Integration with `Container.call_scope`

Today (post `consolidate-principal-bridge`):
```python
async with container.call_scope(
    pre_hook=...,
    scoped_seeds=current_request_principal_seeds(),
) as ...:
```

After this change:
```python
async with container.call_scope(
    pre_hook=...,
    framework_seeds=request_scope.all_seeds(),
) as ...:
```

The `scoped_seeds` → `framework_seeds` rename (BACKLOG) lands in the
same change because the call site changes anyway; doing it together
avoids two churn waves on the same line.

### LDD migration is the riskiest

Principal and request_scope are dispatch-internal; consumers don't see
them. LDD is consumer-facing: every tool body that uses `event()` /
`log()` / `report()` depends on the bridge.

**Behaviour preserved:**
- LDD primitives still work inside any transport-managed scope (every
  transport opens a scope; the LDD seed is published as part of
  scope setup).
- LDD primitives outside a scope still fail — now with a typed
  `RequestScopeMissing(LddState)` instead of `AmbientContextMissing`.
- `__cause__` chain preserves the old exception class via wrapping
  so tests that grep for `AmbientContextMissing` text don't break
  catastrophically (the original message + class are reachable
  through `e.__cause__`).

**Behaviour intentionally improved:**
- A tool body using `event()` without `ctx` declared in its signature
  used to silently work (LDD reached into the ambient). It still
  works — but the error surface is now uniform with Principal/Container
  failures. One pattern to learn.

**Migration step recommendation:** land this change with
`AmbientContextMissing` as a `DeprecationWarning`-emitting subclass of
`RequestScopeMissing(LddState)` for one release. Removes after the
shim deprecation window. Cuts test-text churn to zero in this release.

### Should `error-envelope-side-channel`'s render state join RequestScope?

Sibling change `error-envelope-side-channel` introduces
`_render_state.py` for `RenderedError` per-call carry, keyed by
`id(exc)`. Two options:

**Option A — render state joins RequestScope.**
Publish `RenderedErrorTable` (a `dict[int, RenderedError]`) as a typed
seed. Writers add to the table; readers `get(RenderedErrorTable)`.
Eliminates yet another ContextVar.

**Option B — render state stays a separate, narrow ContextVar.**
The keyed-by-`id(exc)` shape is different enough from "one typed
value per type" that conflating them adds API surface to RequestScope
(now it needs to support "table" seeds, not just typed values).

**Recommendation: Option B.** RequestScope's contract is "one value per
type." A keyed table is a different shape; forcing it through the
same API costs more than it saves. The two changes coexist; they
share the *philosophy* (explicit named side channels over implicit
mutation) without sharing the same code.

This is captured in the proposal's Non-goals; documenting here so the
design isn't revisited later without context.

### What `_pending_typed_envelope` does after both changes land

After `error-envelope-side-channel` lands, `_pending_typed_envelope`
is either retired (the FastMCP middleware reads from
`_render_state.get(exc)` directly) or stays as a separate slot inside
`_render_state.py`. That decision sits in the sibling change's
design, not here.

### The `framework_seeds=` rename rationale

`scoped_seeds=` reads as "any scoped seeds the caller wants to publish."
That's wrong — the parameter is exclusively for **framework-tier**
seeds (Principal, LddState, per-request Container). App-author seeds
go through `pre_hook`'s `seed: SeedFn` parameter (the user tier).

`framework_seeds=` names the contract. BACKLOG explicitly says the
rename should land alongside this generalisation; doing both in one
change is cheaper than two churn waves on the same call site.

### Open question (resolve before tasks)

Should `publish()` be variadic (`publish(*values)`) or always
single-value (`publish(value)`)? Variadic matches the BACKLOG sketch
and is the natural shape for "open a request scope with N seeds at
once." Single-value is simpler but every transport setup site would
make N consecutive calls. **Recommendation: variadic** — matches
substrate usage where the middleware knows everything to publish at
once.
