## Why

The 2026-05-26 structural audit found **three independent `ContextVar`
bridges** sitting at the substrate ↔ dispatch boundary, all with the
same shape and the same failure mode (silent `None` when the writer
hasn't run):

1. **`_request_principal`** — `packages/dispatch/_principal_bridge.py:20-50`.
   Carries `Principal | None`. Writers: 5 substrate sites. Readers:
   `DispatchHookStage`, `AuthorizeGateStage`. This bridge was just
   cleaned up by `consolidate-principal-bridge` (named writer API,
   private to dispatch layer). Pattern is sound for N=1.

2. **`_a2kit_request_scope`** — `packages/di/_request_scope.py:23-26`.
   Carries `Container | None` (the per-request DI scope). Writer:
   `http/build.py:_install_request_scope_middleware`. Reader:
   `di/_fastapi_bridge.py:_make_resolver` (FastAPI `Depends`
   integration). **Silent-failure mode:** if FastAPI resolves a
   dependency before the middleware runs, the contextvar is `None`
   and DI resolution fails silently. No type annotation guards the
   ordering invariant at parse time.

3. **`_LDD_STATE`** — `packages/ldd/ambient.py:46`. Carries
   `_LddState | None`. Writers: `ldd_state_for_call()` (CLI runtime,
   MCP wrapper, test client). Readers: every LDD primitive
   (`event()`, `report()`, `log()`, level shorthands). **The ambient
   trap:** calling any LDD primitive outside `ldd_state_for_call()`
   raises `AmbientContextMissing`. No type annotation documents this
   precondition; tools that don't accept `ctx` have invisible LDD
   dependencies.

The BACKLOG already names the destination
(**"Generalise `_principal_bridge` to `RequestScope` when a second
request-scoped value lands"**) and prescribes the shape: ONE
`ContextVar[dict[type, Any]]` + API
`publish(*values) / get(T) / all_seeds() / reset(token)`. The
condition was sized as N≥2.

**The audit shows N is already 3** — and the third one is the most
painful (LDD ambient trap is a recurring source of test-setup
confusion). The trigger is met.

There's an additional related smell that the audit surfaced and that
sits cleanly inside this same shape:

4. **`_pending_typed_envelope`** — `packages/mcp/_wrappers.py:35`.
   Carries `list[dict[str, Any]] | None` for the
   `McpErrorRenderStage` → `TypedErrorEnvelopeMiddleware` handoff.
   This is being addressed by sibling change
   `error-envelope-side-channel`. **If both changes land,** the
   render-state side channel either uses `RequestScope` or sits
   beside it as its own typed accessor (design.md decides).

## What Changes

- **New** `packages/dispatch/request_scope.py` (or
  `packages/context/request_scope.py` — design.md picks the layer
  carefully) carrying:
  - Public typed API:
    - `publish(*values: object) -> Token` — write one or more typed
      seeds, returning a single token that resets all of them.
    - `get(t: type[T]) -> T` — read a typed seed, raises
      `RequestScopeMissing(t)` with a precise message if absent.
    - `try_get(t: type[T]) -> T | None` — read or None.
    - `all_seeds() -> dict[type, object]` — for `Container.call_scope`
      / `seed_scoped` integration.
    - `reset(token: Token) -> None`.
  - One module-private `ContextVar[dict[type, Any] | None]` underneath.
- **Migrate `Principal`** from `_principal_bridge` to `RequestScope`.
  Substrate writers call `request_scope.publish(principal)`; dispatch
  stages call `request_scope.get(Principal)`. The
  `set_request_principal` / `current_request_principal_seeds` /
  `reset_request_principal` named API stays as a thin compatibility
  wrapper for one release (one-file change, zero behaviour change),
  with a `DeprecationWarning` and BACKLOG entry to remove.
- **Migrate `_a2kit_request_scope`** to `RequestScope`. The per-request
  `Container` becomes one of the typed seeds:
  `request_scope.publish(per_request_container)`. The FastAPI bridge
  reads via `request_scope.get(Container)`. The silent-`None` mode
  becomes a precise `RequestScopeMissing(Container)` raised at the
  earliest read site — caller learns immediately that the middleware
  isn't in the request stack.
- **Migrate `_LDD_STATE`** to `RequestScope`. `ldd_state_for_call()`
  publishes via `request_scope.publish(LddState(...))`; LDD primitives
  read via `request_scope.get(LddState)`. The `AmbientContextMissing`
  exception is replaced by `RequestScopeMissing(LddState)`. **Critical:**
  this preserves the existing "primitives only work inside a
  `ldd_state_for_call()` block" semantics; the change is that the
  failure becomes typed and uniform with the other bridges, and
  documentation pivots to "LDD requires a request scope, opened
  automatically by every transport."
- **Update** `Container.call_scope` to read `request_scope.all_seeds()`
  as its source of framework-tier seeds (replaces the
  `scoped_seeds=current_request_principal_seeds()` call in
  `consolidate-principal-bridge`). The `framework_seeds=` rename
  proposed in BACKLOG happens in the same change.
- **New OpenSpec capability** `request-scope` — owns the bridge
  contract, the typed API, and the failure-mode invariant.
- **Modified capability** `dispatch-pipeline` — dispatch stages read
  request-scoped values via `request_scope.get(T)`, not via
  per-type bridge modules.

## Capabilities

### New Capabilities
- `request-scope` — single typed substrate↔dispatch bridge with
  `publish / get / try_get / all_seeds / reset` API and precise
  `RequestScopeMissing(T)` failures.

### Modified Capabilities
- `dispatch-pipeline` — stages read request-scoped values via
  `request_scope.get(T)`. The per-type `_principal_bridge`,
  `_a2kit_request_scope`, `_LDD_STATE` ContextVars are private
  implementation detail; the public bridge is `RequestScope`.
- `principal-propagation` — the named `set_request_principal` /
  `current_request_principal_seeds` API becomes a deprecation shim
  routed through `request_scope.publish(p) / get(Principal)`.

## Impact

- Affected code: new `packages/dispatch/request_scope.py` (~150 LOC),
  modifications to `packages/dispatch/_principal_bridge.py` (becomes
  a shim), `packages/di/_request_scope.py` (becomes a shim or is
  deleted), `packages/ldd/ambient.py` (becomes a shim or is
  rewritten), `packages/di/container.py` (`call_scope` reads
  `all_seeds`), `packages/dispatch/stages.py` (3 stages read via the
  new API), substrate writers in `packages/auth/`, `packages/mcp/`,
  `packages/http/`.
- No consumer-visible behaviour change. The failure mode for LDD
  primitives outside a scope changes from `AmbientContextMissing` to
  `RequestScopeMissing(LddState)`; a `__cause__` chain preserves
  back-compat for callers grepping exception text in tests.
- Removes 3 (or 4 with envelope) per-type ContextVar bridges. The N+1
  cost of the next request-scoped value (TenantId, TraceContext,
  RequestId — all named in BACKLOG as future candidates) drops to
  zero: it's one `publish` call from the writer side, one `get` call
  from the reader side.
- Static-analysis health: the silent-`None` modes become typed
  exceptions, surfacing precondition failures early.
- Cross-ref: BACKLOG "Generalise `_principal_bridge` to `RequestScope`",
  BACKLOG "Rename `Container.call_scope(scoped_seeds=)` →
  `framework_seeds=`" (lands in the same change),
  `consolidate-principal-bridge` (lands before this), sibling
  `error-envelope-side-channel` (decides whether render state joins
  RequestScope or sits beside it).

## Non-goals

- **Not** removing the substrate-side writers. Every substrate that
  needs to populate request-scoped state still has a 1-line `publish`.
- **Not** changing LDD primitive signatures. `event(...)`, `log(...)`,
  `report(...)` stay as-is.
- **Not** introducing a global `RequestScope` singleton outside
  request handling. Code paths that never run inside a request keep
  failing with `RequestScopeMissing(T)` (this is the *desired*
  behaviour — it surfaces the misuse).
