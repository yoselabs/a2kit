# retire-legacy-di-surface

## Why

The v0.36 / v0.37 waves shipped the new DI surface (`provide`, `get`,
`dispatch`, `child`, `resolve_params`, `has_provider`, `Scope`,
`Resolver`, `Lazy[T]`) and migrated all production dispatch sites
through `Container.dispatch`. The legacy surface remains intact alongside:

- `Container.register(T, factory)` — 0 src/ callers, 16 test sites
- `Container.register_singleton(T, factory)` — 0 src/ callers, 14 test sites
- `Container.resolve(T)` (sync) — 1 src/ caller (TestClient), 19 test sites
- `Container.aresolve(T)` — 0 src/ callers, 10 test sites
- `Container.has(T)` — 0 src/ callers (all migrated to `has_provider`), 5 test sites
- `Container.has_async_singleton(T)` — 0 src/ callers, 4 test sites
- `Container.has_any_async_singletons()` — 0 src/ callers
- The `_singletons` / `_async_factories` / `_async_singleton_locks` /
  `_param_cache` internal state attached to these methods
- The `_resolve_factory_kwargs` / `_aresolve_factory_kwargs` internal
  helpers that power the legacy resolve methods

Two active DI APIs violate CLAUDE.md's "no redundancy / no multiple
ways of doing the same thing" rule. Consumer code authoring against
the legacy surface — visible in tests — risks divergence as the new
surface evolves. The legacy methods also keep dead state on every
`Container` instance (`_singletons` sentinel, async-factory bookkeeping)
that the new resolve path doesn't need.

## What Changes

- **BREAKING**: `Container.register`, `Container.register_singleton`,
  `Container.resolve`, `Container.aresolve`, `Container.has`,
  `Container.has_async_singleton`, `Container.has_any_async_singletons`
  raise `TypeError` with v0.38 migration hints. Hints name the
  replacement (`provide`, `get`, `has_provider`).
- The `_resolve_factory_kwargs` / `_aresolve_factory_kwargs` internal
  helpers are deleted.
- The legacy state (`_singletons` sentinel-cached map,
  `_async_factories`, `_async_singleton_locks`, `_param_cache` keyed
  on legacy factories) is unified with the new resolution path's
  state. Concretely: `_singletons` becomes the app-scope cache used
  by `_build_singleton`; `_async_factories` is removed (provider
  introspection at registration is enough); `_param_cache` stays
  (used by both paths) but its docstring loses the legacy framing.
- The `_override` test seam migrates from "set
  `_providers[T]=lambda: instance` + `_singletons[T]=instance` +
  `_async_factories.discard(T)`" to "set `_providers[T]=lambda:
  instance` + `_singletons[T]=instance` + `_scope_metadata[T] =
  Scope.SINGLETON`".
- `TestClient`'s `override(T, instance)` post-verification path
  switches from `container.resolve(T)` to `await container.get(T)`
  (or eliminates the post-verification step if it's redundant — the
  snapshot/restore seam already pins the instance).
- All test sites exercising legacy methods are retired (when the test
  is duplicate coverage already exercised via the new API) or
  rewritten (when the test pins a unique behavior). Audit doc in
  `tasks.md` enumerates each test site's disposition.

## Impact

- Affected specs:
  - `request-scoped-di` (modified) — remove "Synchronous resolve" requirement,
    update "Container API contains no feature names" + "Per-call result
    caching" to drop `resolve`/`aresolve` mentions, retain `provide` +
    `get` + `Lazy[T]` requirements
- Affected code:
  - `src/a2kit/packages/di/container.py` — ~200 LOC removed (legacy methods + helpers + dead state)
  - `src/a2kit/packages/di/__init__.py` — docstring updates (remove "legacy surface" mentions)
  - `src/a2kit/packages/testing/__init__.py` — TestClient override post-verify migrates to async `get`
- Affected tests:
  - `tests/packages/di/test_container.py` — retire (duplicate coverage in `test_lazy_*`, `test_per_call_*`)
  - `tests/test_cleanup_round_5_6_code_shape.py` — retire (legacy resolve-path unit tests)
  - `tests/test_singleton_async_factories.py` — retire or rewrite as `provide(scope=SINGLETON)` + async factory
  - `tests/test_app_lifecycle_and_di.py` — selective: replace `container().resolve()` with `await app._resolver.get()`
  - `tests/test_canonical_apis.py` — selective updates
  - `tests/test_singleton_type_inference.py` — keep / migrate
  - Other test sites — case-by-case
- Migration: consumer test code calling any legacy method gets a
  `TypeError` with the replacement named in the message. The new API
  has been documented since v0.36 / v0.37 release notes.
