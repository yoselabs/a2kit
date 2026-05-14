# Tasks — retire-legacy-di-surface

## 1. BDD baseline (red tests)

- [x] 1.1 Write failing test `tests/packages/di/test_legacy_retired.py::test_register_raises_with_v038_hint` — `container.register(T)` raises `TypeError` naming `provide` and `v0.38`
- [x] 1.2 Write failing test `tests/packages/di/test_legacy_retired.py::test_register_singleton_raises_with_v038_hint` — `container.register_singleton(T, factory)` raises with hint
- [x] 1.3 Write failing test `tests/packages/di/test_legacy_retired.py::test_resolve_sync_raises_with_v038_hint` — `container.resolve(T)` raises naming `await Container.get`
- [x] 1.4 Write failing test `tests/packages/di/test_legacy_retired.py::test_aresolve_raises_with_v038_hint` — `await container.aresolve(T)` raises (or raises before await)
- [x] 1.5 Write failing test `tests/packages/di/test_legacy_retired.py::test_has_raises_with_v038_hint` — `container.has(T)` raises naming `has_provider`
- [x] 1.6 Write failing test `tests/packages/di/test_legacy_retired.py::test_has_async_singleton_raises_with_v038_hint`
- [x] 1.7 Write failing test `tests/packages/di/test_legacy_retired.py::test_has_any_async_singletons_raises_with_v038_hint`
- [x] 1.8 Write failing test `tests/packages/di/test_legacy_retired.py::test_surface_inventory_matches_spec` — `dir(Container)` public surface = spec-enumerated set
- [x] 1.9 Run `make test`; confirm 8 fail with "DID NOT RAISE TypeError" (red baseline)

## 2. Migrate TestClient + remaining src/ caller

- [x] 2.1 Audit `src/a2kit/packages/testing/__init__.py::override` post-verify path — confirm it's the only src/ legacy call site (currently `container().resolve(type_)`)
- [x] 2.2 Replace `container().resolve(type_)` with `await app_._resolver.get(type_)` OR drop the post-verify if `_snapshot`/`_restore` already pins the override
- [x] 2.3 Run TestClient tests; confirm green

## 3. Replace legacy methods with loud-crash stubs

- [x] 3.1 Replace `Container.register(type_, factory=None)` body with `raise TypeError(...)` naming `provide` + `v0.38`
- [x] 3.2 Replace `Container.register_singleton(type_, factory)` body with `raise TypeError(...)` naming `provide(scope=...)` + `v0.38`
- [x] 3.3 Replace `Container.resolve(type_, *, cache=, chain=)` body with `raise TypeError(...)` naming `await get(T)` + `v0.38`
- [x] 3.4 Replace `Container.aresolve(type_, *, cache=, chain=)` body with `raise TypeError(...)` naming `await get(T)` + `v0.38`
- [x] 3.5 Replace `Container.has(type_)` body with `raise TypeError(...)` naming `has_provider` + `v0.38`
- [x] 3.6 Replace `Container.has_async_singleton(type_)` + `has_any_async_singletons()` bodies with `raise TypeError(...)` + `v0.38`
- [x] 3.7 Delete `_resolve_factory_kwargs` and `_aresolve_factory_kwargs` internal helpers (their only callers — `resolve` and `aresolve` — are now stubs)
- [x] 3.8 Run §1 BDD tests; confirm they pass

## 4. State consolidation

- [x] 4.1 Audit `_async_factories` / `_async_singleton_locks` usage outside legacy methods — confirm they're only referenced by the now-stubbed methods + `_override` / `_snapshot` / `_restore`
- [x] 4.2 Remove `_async_factories: set[type]` initialization (or repurpose for new path if `provide(scope=SINGLETON)` with async factories needs the marker)
- [x] 4.3 Remove `_async_singleton_locks: dict[type, asyncio.Lock]` initialization (the new path uses `_get_locks` for coalescing)
- [x] 4.4 Update `_override` / `_snapshot` / `_ContainerSnapshot` to drop `async_factories` field
- [x] 4.5 Update `_singletons` docstring + initialization: it's now the canonical app-scope cache, not a "registered-but-unresolved sentinel map"
- [x] 4.6 Run full test suite; confirm green

## 5. Test migration

Audit table (filled in during execution):

- [x] 5.1 `tests/packages/di/test_container.py` — disposition: RETIRE; rewrite as a thin smoke test using the new API, OR delete entirely (BDD coverage in `test_lazy_*` / `test_per_call_scope` / `test_cleanup_stack` is comprehensive)
- [x] 5.2 `tests/test_cleanup_round_5_6_code_shape.py` — disposition: REWRITE or RETIRE per audit; tests target legacy `resolve` + `_override` snapshot/restore
- [x] 5.3 `tests/test_singleton_async_factories.py` — disposition: REWRITE using `provide(scope=SINGLETON)` with async factory (same behavior, new API)
- [x] 5.4 `tests/test_app_lifecycle_and_di.py` — selective: replace `container().resolve()` with `await app._resolver.get()` in 8 sites
- [x] 5.5 `tests/test_canonical_apis.py` — selective updates
- [x] 5.6 `tests/test_singleton_type_inference.py` — uses `register_singleton` for type-inference tests; migrate to `provide` (which routes through the same `resolve_singleton_args` helper)
- [x] 5.7 `tests/test_testing_di_override.py` — uses `register` heavily; migrate to `provide`
- [x] 5.8 Other `register` / `register_singleton` / `resolve` / `aresolve` / `has` test sites — migrate per audit
- [x] 5.9 Run full test suite; confirm green

## 6. Spec + lint cleanup

- [x] 6.1 Update `openspec/specs/request-scoped-di/spec.md` "Container API contains no feature names" + "Per-call result caching" requirements to drop `resolve`/`aresolve` mentions (the canonical spec edit happens via archive)
- [x] 6.2 Confirm `make lint` clean (no new lint rule needed — the legacy methods themselves enforce migration via `TypeError`)
- [x] 6.3 Confirm `a2kit lint static src/` clean for all A2K0XX codes

## 7. Documentation + CHANGELOG

- [x] 7.1 Update `docs/patterns/test-overrides.md` if it references `container.resolve` (audit)
- [x] 7.2 Add CHANGELOG `Unreleased — v0.38 (retire-legacy-di-surface)` section with the migration table:
  | Removed | Replacement |
  |---|---|
  | `Container.register(T, factory)` | `Container.provide(T, factory)` |
  | `Container.register_singleton(T, factory)` | `Container.provide(T, factory, scope=Scope.SINGLETON)` |
  | `Container.resolve(T)` | `await Container.get(T)` (async) |
  | `Container.aresolve(T)` | `await Container.get(T)` |
  | `Container.has(T)` | `Container.has_provider(T)` |
  | `Container.has_async_singleton(T)` | (removed; framework no longer distinguishes async vs sync at the registration level) |
  | `Container.has_any_async_singletons()` | (removed) |
- [x] 7.3 Update `~/Documents/Knowledge/Agents/Claude/project_a2kit_design_state.md` with the v0.38 surface

## 8. Archive + release

- [x] 8.1 `openspec validate retire-legacy-di-surface --strict` clean
- [x] 8.2 `make lint` + `make test` clean
- [x] 8.3 `openspec archive retire-legacy-di-surface`
- [x] 8.4 Confirm `openspec/specs/request-scoped-di/spec.md` updated post-archive
- [x] 8.5 Bump `pyproject.toml` version 0.37.0 → 0.38.0; date the CHANGELOG entry
- [x] 8.6 Commit `chore: release v0.38.0`; tag `v0.38.0`; push commit + tag
