# Design — retire-legacy-di-surface

## Context

Two parallel DI APIs are in place after v0.37. The new surface
(`provide` / `get` / `dispatch` / `child` / `has_provider` /
`resolve_params` / `Lazy[T]` / `Scope` / `Resolver`) is the documented
API; the legacy surface (`register` / `register_singleton` / `resolve`
/ `aresolve` / `has` / `has_async_singleton`) lingers with zero remaining
framework callers but ~63 test sites still exercising it.

CLAUDE.md is explicit: "No redundancy / no multiple ways of doing the
same thing". This change removes the legacy surface and consolidates
container state on the new path.

## Decisions

### D1 — Loud-crash via `TypeError`, no deprecation period

**Decision.** Replace each legacy method body with a `raise TypeError(...)`
that names the replacement, the version, and the migration recipe.
Pattern matches the v0.36 retirement of `App.singleton` / etc.

**Reason.** CLAUDE.md "no backward compatibility shims" and the v0.33+
loud-crash convention. Forces consumers' migration into their commit
history rather than letting drift hide.

**Alternative.** Underscore-prefix the methods (rename to
`_register`, `_resolve`, etc.) so they remain accessible to framework
internals but disappear from the public surface. Rejected — there are
no remaining framework internal callers post-migration; underscore
methods would still leak across the standalone-DI-package boundary.

### D2 — Unify container state on the new path

**Decision.** Remove `_async_factories: set[type]` and
`_async_singleton_locks: dict[type, asyncio.Lock]` (the legacy async
bookkeeping). The new path uses `_get_locks` for concurrent-first-touch
coalescing on app-scope resolution. `_singletons` becomes the
canonical app-scope cache (post-migration; legacy code used
`_UNRESOLVED` sentinel + late population, the new path stores the
resolved instance directly).

**Reason.** The two state machines drifted: new-path `_singletons`
holds resolved instances; legacy-path `_singletons` held an
`_UNRESOLVED` sentinel until first sync `resolve()`. After retirement,
only the resolved-instance shape is used.

### D3 — TestClient override post-verify becomes async or removed

**Decision.** The current `TestClient.override(T, instance)` path
ends with `app_.container().resolve(type_)` as a sanity check that the
override stuck. Replace with `await app_._resolver.get(type_)` (async
context — TestClient is already async). If the snapshot/restore seam
already guarantees the override holds, drop the post-verify entirely.

**Reason.** Sole remaining `src/` caller of legacy `resolve`. The new
`get` honors lifecycle but for a pre-resolved instance it returns
from cache without entering anything.

**Alternative.** Keep the legacy `resolve` as a private
`Container._resolve_for_test` method. Rejected — adds a "test-only
back door" that violates the standalone-shippable invariant.

### D4 — Test migration strategy: retire vs. rewrite per file

**Decision.** Three dispositions per test site:

1. **Retire** when the test is a direct unit test of a legacy method
   AND the same behavior is already covered by `tests/packages/di/test_lazy_*`,
   `test_per_call_scope.py`, `test_cleanup_stack.py`, etc. via the
   new API. `tests/packages/di/test_container.py` is mostly this.
2. **Rewrite** when the test pins behavior unique to that file. Replace
   `container.register(T)` → `container.provide(T)`; replace
   `container.resolve(T)` → `await container.get(T)` (test fixture
   becomes async). `tests/test_app_lifecycle_and_di.py` is mostly this.
3. **Retire the file** when every test in it covers removed v0.35
   spec behavior (singleton-async-factories specifically targets
   legacy `register_singleton` with `async def` factories — the new
   `provide(scope=SINGLETON)` accepts the same).

The audit table lives in `tasks.md` per file.

### D5 — Bridge in `aresolve` becomes dead

The v0.36 bridge in `aresolve` that routed `_scope_metadata`-tagged
types to `Container.get` was a temporary integration patch. With
`aresolve` removed, the bridge goes too.

### D6 — `_override` seam stays

The `_override` / `_snapshot` / `_restore` triple is the TestClient's
test-only seam for `override(T, fake)`. It mutates internal state in
place and rolls back at session exit. The seam stays — but its
internal state references migrate to the new path (D2).

## Non-goals

- `Container.singletons()`, `Container.has_singleton()` — already
  retired at the App level in v0.36; the Container itself never
  exposed `singletons()` publicly.
- Renaming `_singletons` internal attribute to something less
  Container-state-confusing (e.g., `_app_cache`). Tidiness sweep
  for a follow-up — public API names are what matter.
- Removing `register_wire_scope` / `wire_scopes` / `wire_scopes_used_by`
  / `_wire_scopes` — these are the wire-side seam consumer packages
  hook into; out of scope for DI surface retirement.

## Risk + rollback

The change is mechanically isolated to `container.py` + `testing/__init__.py`
+ test files. If a consumer outside the test suite was depending on
the legacy methods (unlikely — they were never in the public surface
docs), they get a clear `TypeError` with a migration recipe and can
adopt the new API in a single commit. Rollback is `git revert`.

The 916-test baseline keeps the safety net: any regression in the
new-path behavior (caused by state-unification or TestClient migration)
surfaces immediately.
