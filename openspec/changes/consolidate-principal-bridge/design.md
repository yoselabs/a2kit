## Context

This change closes work that `principal-single-source` (archived
2026-05-26) started but only fig-leafed. The audit identified one
piece of data (Principal) carried through three storage layers
(ContextVar → magic-string wire kwarg → DI SCOPED provider). The
previous change isolated the contextvar read to one helper so
`stages.py` was grep-clean; it left the dual-path and the implicit
DI-via-dict-iteration unchanged.

The user reframe (2026-05-26) clarified the principle to honor:
**robust, simple, verifiable; magic only when bridging is required.**
Spike findings: substrate-native ambients (FastMCP `Context.set_state`,
ASGI `request.state`) work but trade one bridge for two and add
framework-specific learning cost. Stdlib `contextvars` is the simplest
explicit bridge. The wrong move is replacing it; the right move is
keeping it, naming it, and killing the magic stacked on top of it.

## Goals / Non-Goals

**Goals:**

- ONE explicit bridge between substrate auth boundary and per-call
  DI scope, named and structurally enforced.
- ContextVar declaration lives in a private dispatch module; no L0
  re-export; writers import named functions, not the raw ContextVar.
- Explicit `Container.seed_scoped(type_, value)` is the only way to
  register a per-call SCOPED instance. Implicit registration by dict
  iteration is removed.
- `stages.py` grep gate becomes structural (private-module import
  boundary) — no future drift possible without crossing an explicit
  layer-private import.
- Two concerns separated cleanly: **ContextVar for ambient
  request-scoped data; DI for typed dependency resolution.** One
  documented bridge between them.

**Non-Goals:**

- Switching to substrate-native ambient state (FastMCP set_state,
  Starlette request.state) — spike-confirmed not simpler.
- Eliminating the ContextVar — it's the right primitive for the job.
- Adding `Annotated`-metadata authorization (FastAPI Security-style)
  to a2kit's surface — `authorize=` already provides the
  block-before-body guarantee.
- Refactoring how Principal arrives at the substrate auth boundary
  (those mechanisms are substrate-owned).
- Changing the `principal: Principal` resolution path in tool bodies
  / `authorize=` callables — DI by type stays.

## Decisions

### 1. Bridge module: `a2kit.packages.dispatch._principal_bridge`

```
packages/dispatch/_principal_bridge.py    # PRIVATE, L4 dispatch
├─ _request_principal: ContextVar[Principal | None]  (module-private)
├─ set_request_principal(p: Principal) -> Token
├─ reset_request_principal(token: Token) -> None
└─ current_request_principal() -> Principal | None
```

- Module is `_`-prefixed: convention for private.
- The ContextVar itself is module-private (`_request_principal`),
  not re-exported. Even consumers of this module can only call the
  named API.
- Lives in dispatch layer (L4). Substrate adapters (L5: `auth`,
  `mcp`, `http`) import downward — clean A2K-LAYER edge.
- The bridge module is added to `_KERNEL_MODULES` is **NOT** correct
  (dispatch ≠ kernel). It's a dispatch-package-internal module —
  picked up by the dispatch layer's normal lint rule.

**Alternative rejected: keep the contextvar in `packages/context`.**
That's where the previous change left it. The L0 placement gave us
public-ish exposure (in `__all__`) that the underscore prefix
contradicted. The whole point is to make the boundary structural.

**Alternative rejected: dispatch-layer kernel module
(`packages/dispatch/__init__.py` exports).** Re-exporting from
`packages/dispatch/__init__.py` makes the bridge front-door visible,
which defeats the point. The bridge module is intentionally a private
sibling to `stages.py` / `substrate.py`.

### 2. Named writer API instead of raw `.set()` / `.reset()`

Substrate writers do:

```python
from a2kit.packages.dispatch._principal_bridge import (
    set_request_principal,
    reset_request_principal,
)

async def on_call_tool(self, context, call_next):
    principal = _build_principal(context)
    if principal is None:
        return await call_next(context)
    token = set_request_principal(principal)
    try:
        return await call_next(context)
    finally:
        reset_request_principal(token)
```

Why named functions over re-exporting the ContextVar:

- The named API is greppable. Searching `set_request_principal` finds
  every writer; searching `_request_principal.set` would also find
  the bridge's internal use.
- If the underlying mechanism ever needs to change (e.g., a
  per-substrate side-table for some edge case), call sites don't move.
- Removes the temptation to call `.get()` from writers — the API
  exposes only writer verbs to writers.

### 3. Reader API: `current_request_principal()` returns `Principal | None`

One reader function. Returns `None` when no substrate has set the
contextvar (unauthenticated transport). Stages that need Principal
in the DI scope call this and then seed if non-None:

```python
# stages.py — DispatchHookStage._wrapped
async with container.child() as child:
    p = current_request_principal()
    if p is not None:
        child.seed_scoped(Principal, p)
    async with child.call_scope(fn, kwargs, pre_hook=hook) as merged:
        ...
```

Wait — this conflicts with `call_scope` opening its own child. Resolved
in Decision 5.

### 4. `Container.seed_scoped(type_, value)` — explicit public API

```python
class Container:
    def seed_scoped(self, type_: type, value: Any) -> None:
        """Register `value` as a SCOPED provider for `type_` on this
        (child) container. May be called only on a child container
        opened via `child()` or inside a `call_scope` body."""
        if self._parent is None:
            raise TypeError(
                "seed_scoped() requires a child container. "
                "Open one via container.child() or call inside call_scope."
            )
        self._providers[type_] = lambda v=value: v
        self._scope_metadata[type_] = Scope.SCOPED
        self._scoped_cache[type_] = value
```

- Public method on `Container`.
- Refuses to operate on a root container (a parent container is
  app-lifetime; SCOPED registrations there would leak across calls).
- Idempotent on the same type within one scope: last-write-wins,
  matching `provide()` semantics.
- Visible at the call site: the registration *is* the line of code.

**Alternative rejected: separate `seed=` kwarg on `call_scope`.** The
explicit method works in more contexts (inside pre_hook, inside
substrate wrappers that open their own child). Single API beats two
ways to do the same thing.

**Alternative rejected: keep the implicit wire-by-type loop AS WELL
as add `seed_scoped`.** Two paths to the same outcome is the original
sin. Pick one.

### 5. `Container.call_scope` no longer implicitly seeds from `wire.values()`

The current loop:

```python
for _wire_val in wire.values():
    _t = type(_wire_val)
    child._providers[_t] = lambda v=_wire_val: v
    # ...
```

is **removed**. Wire kwargs return to their literal meaning: named
values to pass to `pre_hook` and to the function's own parameters.

Migration for the existing pre_hook consumers (connection resolution
in `packages/connections/`): the pre_hook contract changes so the
hook receives the child container or a `seed` callable. Decision 6
covers the signature.

### 6. `pre_hook` contract update

Current:
```python
pre_hook(fn, wire_kwargs: dict) -> dict[str, Any]
```

Updated:
```python
pre_hook(fn, wire_kwargs: dict, seed: SeedFn) -> dict[str, Any]

class SeedFn(Protocol):
    def __call__(self, type_: type, value: Any) -> None: ...
```

Hooks that publish typed instances call `seed(TrackerConn, conn)`
before returning. The returned dict is still merged into wire kwargs
by name as before.

**Alternative considered: pass the child container directly.** Cleaner
in some ways (the hook can do anything), more invasive in others
(exposes the container's full API to hook authors, including
`provide()` which would error on a sealed parent). The minimal
`SeedFn` keeps the hook's mental model tight.

**Alternative rejected: keep implicit walk for one release as
deprecation.** Adds half-magic, half-explicit state. The repo has
two in-repo pre_hook consumers (the connections package); migrating
them is a few-line change. Clean break is verifiable.

### 7. `_apply_authorize_gate` simplification

Current shape:
```python
async def _gated(**kwargs):
    principal = next((v for v in kwargs.values() if isinstance(v, _Principal)), None)
    token = _a2kit_request_principal.set(principal) if principal is not None else None
    try:
        await _run_authorize_gate(authorize, container)
        return await wrapped(**kwargs)
    finally:
        if token is not None:
            _a2kit_request_principal.reset(token)
```

After: the FastAPI `Security` guard already places Principal in
kwargs. `_run_authorize_gate` opens its own child container and seeds
Principal explicitly from the bridge:

```python
async def _gated(**kwargs):
    await _run_authorize_gate(authorize, container)
    return await wrapped(**kwargs)

# stages.py
async def _run_authorize_gate(authorize, container):
    async with container.child() as child:
        p = current_request_principal()
        if p is not None:
            child.seed_scoped(Principal, p)
        async with child.call_scope(authorize, {}) as merged:
            # ...resolve and invoke
```

The kwargs-scan-and-stuff dance disappears. The contextvar was already
written by the time `_apply_authorize_gate` runs — `_lift_principal_into_scope`
(in `dispatch/substrate.py`) calls `set_request_principal` before the
authorize gate. No re-publication needed.

**Verify in tasks:** `_lift_principal_into_scope` is invoked
upstream of `_apply_authorize_gate` on the HTTP path. If true (it is,
per current code), the kwargs-scan is redundant. If false, the
authorize gate gets the seed via the new explicit `seed_scoped`
call directly from kwargs.

### 8. `auth/testing.py:using_principal` is DELETED (locked 2026-05-26)

User decision: redundant when the named bridge writer API exists.
Test fixtures that don't have an `App` in hand call the writer API
directly:

```python
from a2kit.packages.dispatch._principal_bridge import (
    set_request_principal,
    reset_request_principal,
)

token = set_request_principal(p)
try:
    ...
finally:
    reset_request_principal(token)
```

Tests with an `App` use the standard DI override:
`app.container().provide(Principal, lambda: fake)`.

The `using_principal` contextmanager wrapped two stdlib lines —
removing it pays a 3-line cost per test site for one less name to
learn, which matches the "simple, verifiable" principle.

## Risks / Trade-offs

- **[Risk]** External code importing `_a2kit_request_principal` from
  `packages/context` breaks. → Mitigation: the symbol is `_`-prefixed
  AND its position in `__all__` is, frankly, my fault — but it's
  been there since `add-auth`. CHANGELOG entry under "Breaking
  (internal API)" with the import-path migration recipe.
- **[Risk]** Pre_hook consumers outside this repo break when the
  implicit wire-by-type loop disappears. → Mitigation: a2kit is
  framework-agnostic but the pre_hook surface isn't documented as
  external API; only in-repo consumer is the connections package.
  Spec deprecation note in the package docstring.
- **[Risk]** The `seed_scoped` "child-only" restriction trips someone
  trying to call it on the root container. → Mitigation: clear
  TypeError with the recipe in the message. Tests cover the
  restriction.
- **[Trade-off]** Two APIs survive: `Container.provide` (app-scope
  SINGLETON/SCOPED registration with full validation) and
  `Container.seed_scoped` (child-only SCOPED registration without
  the seal check). → Accepted: they have distinct use cases
  (registration vs. per-call seed); collapsing would require
  reworking the seal contract.
- **[Trade-off]** The bridge module is dispatch-layer (L4). A future
  "ambient locale" or "ambient tracing-span" feature would want the
  same pattern but might not belong in dispatch. → Accepted: when
  the second case shows up, refactor to a generic
  `packages/dispatch/_ambient/` package. For one consumer, the
  named module is right-sized.

## Migration Plan (single-shot clean break, locked 2026-05-26)

User decision: no backward-compat shims, no migration window.
One coherent diff lands all changes; the test gates catch any
miss. The order below is the implementation order inside a single
PR/commit, not a multi-PR sequence.

1. **Add `Container.seed_scoped`** + tests.
2. **Remove the implicit wire-by-type loop** in
   `Container.call_scope`. Update its docstring.
3. **Update the `pre_hook` signature** to
   `(fn, wire_kwargs, seed)`. Migrate in-repo pre_hook consumers
   (`packages/connections/`).
4. **Create `packages/dispatch/_principal_bridge.py`** with the
   declaration and named API. The ContextVar declaration moves
   here from `packages/context/principal.py` — no re-export, no
   shim. `packages/context/principal.py` returns to carrying only
   the `Principal` dataclass.
5. **Remove `_a2kit_request_principal`** from
   `packages/context/__init__.py:__all__`.
6. **Migrate substrate writers** to the named API in one pass:
   `auth/api_key.py`, `mcp/principal_middleware.py`,
   `http/build.py`, `dispatch/substrate.py:_lift_principal_into_scope`.
7. **Delete `auth/testing.py:using_principal`** entirely. Migrate
   in-repo tests that used it to either the named writer API
   directly or `app.container().provide(Principal, fake)`.
8. **Migrate stages** to read via `current_request_principal()` and
   seed via `child.seed_scoped(Principal, p)`. Simplify
   `_apply_authorize_gate` (drop the kwargs-scan dance).
9. **Delete `_principal_scope.py`** and the magic string
   `"_a2kit_principal"` everywhere.
10. **Drop the grep-based stage-source test** from
    `tests/test_principal_single_source.py`; replace with the
    structural import-boundary check.

Rollback: full revert of the diff. The change is atomic by design.

## Open Questions (resolved 2026-05-26)

- ~~Should `Container.seed_scoped` accept a `factory` (callable)
  alongside a `value` (instance)?~~ **Decided: instance-only.**
  Matches the per-call use case; factories live on `provide()`.
- ~~Should the pre_hook `seed` parameter be optional or required?~~
  **Decided: required.** User confirmed clean break is acceptable.
- ~~Should we name the bridge module generically for future
  ambient data (locale, tracing span)?~~ **Decided: name it
  `_principal_bridge.py` for the one concern.** Refactor to
  `_ambient/` when a second concern lands (YAGNI).
- ~~Migration window for the `packages/context` re-export?~~
  **Decided: no migration window.** Clean break in one commit.
- ~~Keep `auth/testing.py:using_principal` as a contextmanager?~~
  **Decided: delete it.** Redundant when the named bridge writer
  API exists; tests use the API directly or DI override.
