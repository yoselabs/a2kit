## 1. BDD specs (write tests first)

- [x] 1.1 `tests/capabilities/request_scope/test_publish_get_round_trip.py` — `publish(Principal(...))` then `get(Principal)` inside the same scope returns the same instance.
- [x] 1.2 `tests/capabilities/request_scope/test_get_missing_raises_typed.py` — `get(Principal)` with no prior `publish` raises `RequestScopeMissing(Principal)` carrying `.requested_type == Principal` and a precise message.
- [x] 1.3 `tests/capabilities/request_scope/test_try_get_missing_returns_none.py` — `try_get(Principal)` with no prior `publish` returns `None` without raising.
- [x] 1.4 `tests/capabilities/request_scope/test_publish_variadic.py` — `publish(principal, ldd_state, container)` succeeds; each is independently retrievable.
- [x] 1.5 `tests/capabilities/request_scope/test_reset_clears_all.py` — `token = publish(a, b, c); reset(token)` clears every value the publish set; subsequent `get(...)` raises.
- [x] 1.6 `tests/capabilities/request_scope/test_last_publish_wins.py` — publishing two `Principal` values, the second `publish` shadows the first; `get(Principal)` returns the second.
- [x] 1.7 `tests/capabilities/request_scope/test_concurrent_scopes_isolated.py` — two concurrent tasks each open a scope with their own Principal; neither sees the other's value.
- [x] 1.8 `tests/capabilities/request_scope/test_all_seeds_returns_copy.py` — `all_seeds()` returns a snapshot; mutating the returned dict does NOT affect the scope.
- [x] 1.9 `tests/capabilities/request_scope/test_principal_via_scope.py` — dispatch stage reads Principal via `request_scope.get(Principal)`; existing Principal-propagation BDD scenarios still pass.
- [x] 1.10 `tests/capabilities/request_scope/test_ldd_state_via_scope.py` — LDD primitives work inside a `request_scope.publish(LddState(...))` block; outside, they raise `RequestScopeMissing(LddState)` (or its deprecation-shim subclass `AmbientContextMissing`).
- [x] 1.11 `tests/capabilities/request_scope/test_request_container_via_scope.py` — FastAPI bridge resolves a typed `Depends` via `request_scope.get(Container)`; with no middleware, the bridge raises `RequestScopeMissing(Container)`.
- [x] 1.12 `tests/capabilities/dispatch_pipeline/test_framework_seeds_param_rename.py` — `Container.call_scope(framework_seeds=...)` works; the old `scoped_seeds=` keyword is a deprecation-shim emitting `DeprecationWarning`.

## 2. Build `RequestScope`

- [x] 2.1 New module `src/a2kit/packages/dispatch/request_scope.py` implementing the API in design.md (`publish`, `get`, `try_get`, `all_seeds`, `reset`, `RequestScopeMissing`).
- [x] 2.2 Module-private `ContextVar[dict[type, Any] | None]` underneath; module docstring documents the substrate↔dispatch contract.
- [x] 2.3 `__all__ = ("publish", "get", "try_get", "all_seeds", "reset", "RequestScopeMissing")` — `ContextVar` is NOT re-exported.

## 3. Migrate Principal

- [x] 3.1 `packages/dispatch/_principal_bridge.py` becomes a thin compatibility shim: `set_request_principal(p)` calls `request_scope.publish(p)` and stores the returned token in a module-local map keyed by `id(token)` so `reset_request_principal(token)` can call `request_scope.reset(token)`. `current_request_principal_seeds()` returns `{Principal: request_scope.get(Principal)}` if present, else `{}`.
- [x] 3.2 Each shim function emits `DeprecationWarning` pointing at `request_scope.publish` / `request_scope.get(Principal)`.
- [x] 3.3 Substrate writers in `packages/auth/`, `packages/mcp/principal_middleware.py`, `packages/http/build.py`, `packages/auth/testing.py` migrate to `request_scope.publish(p)` directly; the shim stays for one-release out-of-tree compatibility.
- [x] 3.4 Dispatch stages (`DispatchHookStage`, `AuthorizeGateStage`) read via `request_scope.get(Principal)` (or `try_get` where None is valid).

## 4. Migrate `_a2kit_request_scope`

- [x] 4.1 `packages/di/_request_scope.py` shim: `set(scope)` calls `request_scope.publish(scope)`.
- [x] 4.2 `packages/di/_fastapi_bridge.py:_make_resolver` reads via `request_scope.get(Container)`. The silent-`None` mode becomes the typed `RequestScopeMissing(Container)` with a clear "FastAPI Depends ran before a2kit middleware" error message.
- [x] 4.3 `packages/http/build.py:_install_request_scope_middleware` writes via `request_scope.publish(scope)` instead of `_a2kit_request_scope.set(scope)`.

## 5. Migrate `_LDD_STATE`

- [x] 5.1 `packages/ldd/ambient.py:_LDD_STATE` ContextVar is retired (or kept as a no-op shim for one release if external tests grep its name).
- [x] 5.2 `ldd_state_for_call(...)` context manager calls `request_scope.publish(LddState(...))` on enter, `request_scope.reset(token)` on exit.
- [x] 5.3 LDD primitives (`event`, `report`, `log`, level shorthands in `packages/ldd/__init__.py`) read via `request_scope.get(LddState)`.
- [x] 5.4 `AmbientContextMissing` becomes a deprecation-shim subclass of `RequestScopeMissing(LddState)` — raised paths chain via `raise from`; one-release window before deletion.

## 6. `Container.call_scope` integration + rename

- [x] 6.1 `Container.call_scope` accepts `framework_seeds: dict[type, Any] | None` as the new public parameter.
- [x] 6.2 `scoped_seeds=` becomes a deprecation-shim keyword — forwards to `framework_seeds=` with a `DeprecationWarning` pointing at the rename.
- [x] 6.3 Every dispatch stage call site updates to `framework_seeds=request_scope.all_seeds()` instead of `scoped_seeds=current_request_principal_seeds()`.

## 7. Capability specs

- [x] 7.1 Land `request-scope` capability (this change's `specs/request-scope/spec.md`).
- [x] 7.2 Modify `dispatch-pipeline` (this change's `specs/dispatch-pipeline/spec.md`) — stages read via `request_scope.get(T)`.
- [x] 7.3 Modify `principal-propagation` — the named API is a deprecation shim. (Apply as a delta in this change's specs OR as a follow-up patch on the existing spec; design.md picks one.)

## 8. Docs

- [x] 8.1 New `docs/patterns/request-scope-bridge.md` — short narrative covering the typed-publish-and-get pattern, the failure mode, when to publish, when to read.
- [x] 8.2 ANTIPATTERNS.md — add "Don't add a new `_<x>_bridge.py` or per-type ContextVar for request-scoped values. Publish through `request_scope` instead."
- [x] 8.3 Update `AGENTS.md` (and `CLAUDE.md` overlay if needed) — reference the new bridge.
- [x] 8.4 `CHANGELOG.md` `[Unreleased]` — flag the unification; flag the deprecation shims.
- [x] 8.5 BACKLOG: collapse "Generalise `_principal_bridge` to `RequestScope`" and "Rename `Container.call_scope(scoped_seeds=)` → `framework_seeds=`" into one done entry once this lands.

## 9. Verification

- [x] 9.1 `make test` green.
- [x] 9.2 `grep -rn "ContextVar" src/a2kit/packages/` shows ContextVars only in `request_scope.py` and (deprecation-shim window) the legacy bridges.
- [x] 9.3 A FastAPI route with no a2kit request middleware in the stack gets `RequestScopeMissing(Container)` with a clear message — not silent failure.
- [x] 9.4 A test calling `event(...)` outside `ldd_state_for_call(...)` gets `RequestScopeMissing(LddState)` (or `AmbientContextMissing` if relying on the shim window).
- [x] 9.5 Adding a hypothetical 4th request-scoped type (TenantId) requires: one new `publish(tenant_id)` at the substrate seam, one new `get(TenantId)` at the read site, zero new ContextVars, zero new bridge modules.
