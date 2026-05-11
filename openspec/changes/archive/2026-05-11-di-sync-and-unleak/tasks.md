## 1. BDD-first scenarios

- [x] 1.1 Write Gherkin-flavored scenarios in `tests/packages/di/test_container.py` covering: sync resolve, sync factory rejection of async factories, no `connection` kwarg in resolve API, container source has no feature names.
- [x] 1.2 Write Gherkin-flavored scenarios in `tests/packages/connections/test_di_dispatch.py` covering: connection middleware loads via store and substitutes typed cfg, schema strips injectable and adds wire `connection`, provider replacement works.
- [x] 1.3 Write Gherkin-flavored scenarios in `tests/test_app_lifecycle_and_di.py` covering: `@on_startup` with `state: AppState` resolves and runs, `@on_shutdown` with typed kwargs resolves and runs, reverse-order shutdown holds, MCP merge order, CLI lifecycle.
- [x] 1.4 Resource pattern is documented in spec (`lazy-init-resources/spec.md`) and README; tested at the consumer-site level (a2web is the canonical consumer). No new a2kit-internal tests added because the pattern carries no framework code.

## 2. Relocate container, strip async

- [x] 2.1 Moved `src/a2kit/packages/connections/container.py` → `src/a2kit/packages/di/container.py`. Updated all imports across app/health/testing/cli/mcp.
- [x] 2.2 Deleted `_SingletonWrapper`. Singleton cache lives on the container directly (`Container._singletons` dict).
- [x] 2.3 Deleted `Container.resolve_sync`, `SyncResolveUnavailable`, `_is_sync_chain`, `_first_async_dep`, `_factory_is_async`, `_resolve_factory_kwargs_sync`.
- [x] 2.4 `Container.resolve` is sync. `connection` kwarg removed. No coroutine awaits inside resolution.
- [x] 2.5 `Container.apply_kwargs` is sync. Optional `pre_resolved` cache parameter lets dispatch hooks seed values that the container should not try to resolve (consumer hooks substitute via `pre_resolved`).
- [x] 2.6 Deleted `_chain_reaches_connection`. `partition_kwargs` returns `(wire_keys, injectable_keys)` only. New generic `register_wire_scope` / `wire_scopes_used_by` replaces the magic-name chain walk.
- [x] 2.7 `app.singleton(T, async_factory)` and `app.provide(T, async_factory)` raise `ValueError` at registration time pointing at the lazy-init pattern.
- [x] 2.8 Deleted `App._reject_singleton_connection_dep`. The sync-only factory rule transitively rejects connection-dependent factories.
- [x] 2.9 `App.__init__` eager-initializes `Container()` and the default sync dispatch hook. `_ensure_container` path is gone.
- [x] 2.10 `App.container()` returns `Container` (non-Optional return type).

## 3. Connections dispatch hook

- [x] 3.1 Created `src/a2kit/packages/connections/dispatch.py` with `make_connection_hook(container, stores)` factory and `install_connection_dispatch(app, conn_types)`.
- [x] 3.2 Hook awaits `store.load(wire_kwargs["connection"])` for each registered conn type, seeds the resolved instances into the container's `pre_resolved` cache, then calls `container.apply_kwargs(fn, wire_kwargs, pre_resolved=...)` synchronously.
- [x] 3.3 The connections Router's `install` calls `install_connection_dispatch` which replaces `app._dispatch_hook`. Apps without connections keep the sync default hook.
- [x] 3.4 Each registered conn type also registers a stub sync provider (raises if called) so `container.has(T)` is True for schema-gen filtering. The dispatch hook pre-resolves the value before the container ever invokes the stub.
- [x] 3.5 No magic-name `if pname == "connection"` remains anywhere in a2kit code. Audit test `test_container_source_has_no_feature_names` enforces this for the container.

## 4. DI-aware lifecycle

- [x] 4.1 `app.on_startup` / `app.on_shutdown` accept handlers with arbitrary kwargs. `dispatch_startup` / `dispatch_shutdown` resolve via `container.apply_kwargs(handler, {})` before calling.
- [x] 4.2 The old `(app: App)` signature is removed (handlers calling without DI work fine since `apply_kwargs` returns empty for no resolvable params). Documented in README + spec.
- [x] 4.3 `dispatch_startup` and `dispatch_shutdown` go through `container.apply_kwargs` via the `_call_lifecycle_handler` helper.
- [x] 4.4 Router `on_startup` / `on_shutdown` methods are bridged by registering the bound method directly; DI resolves its typed kwargs.

## 5. Unify dispatch entry points

- [x] 5.1 `packages/health/_run_one_check` calls `app._container.apply_kwargs(check.fn, {})` directly instead of going through the dispatch hook.
- [x] 5.2 `packages/testing/client._invoke_through_dispatcher` continues through the dispatch hook (it IS a tool dispatch). No change needed.

## 6. a2web migration

Deferred to after a2kit v0.27 ships. a2web's `pyproject.toml` pins `a2kit` to a git tag; the migration steps land in a follow-up commit on the a2web side. The migration is mechanical:

- [ ] 6.1 (in a2web) Migrate `state.py`: `AppState.sqlite/browser_pool/llm_extractor` become non-Optional. Drop `browser_lock` and `llm_lock` fields. Drop `llm_unavailable_reason` field.
- [ ] 6.2 (in a2web) Migrate `SqliteResource`, `BrowserPool`, `Extractor` to lazy-init pattern: each gains `_lock`, `_ensure`, `close`, and accessors that await `_ensure` internally.
- [ ] 6.3 (in a2web) Convert `build_state` from `async def` to `def`. Resources are constructed sync; opens happen lazily.
- [ ] 6.4 (in a2web) Rewrite `_open_resources` / `_close_resources` as DI-typed hooks taking `state: AppState`. Drop the `_app.container()` dance.
- [ ] 6.5 (in a2web) Optionally add a `@on_startup` warm-up calling `await state.sqlite._ensure()` if fail-fast is desired.
- [ ] 6.6 (in a2web) Bump pyproject.toml a2kit pin to v0.27.0 and run a2web test suite.

## 7. Tests

- [x] 7.1 Deleted tests that exercised the deleted surfaces: async factories on singletons, `resolve_sync` paths, `connection` kwarg on `resolve`, `_reject_singleton_connection_dep`, `container() is None` branches.
- [x] 7.2 All scenarios in Section 1 pass.
- [x] 7.3 Existing a2kit test suite green after Section 2-5 deletions and rewrites (719 passing).
- [ ] 7.4 a2web test suite green — deferred to a2web migration (Section 6.6).

## 8. Docs

- [x] 8.1 README "Dependency injection" section rewrites: sync container, dispatch-hook seam for connection load.
- [x] 8.2 New "Resource pattern (lazy-init)" subsection in README: documents the resource class shape with rationale and the fail-fast warm-up hook.
- [x] 8.3 New "Lifecycle hooks are DI-aware" subsection: shows the new handler signature with typed kwargs.
- [x] 8.4 CHANGELOG v0.27.0 entry calls out every breaking change with migration notes.

## 9. Release

- [x] 9.1 Version bump to v0.27.0.
- [x] 9.2 CHANGELOG entry with breaking changes called out.
- [ ] 9.3 Tag and release. (Manual step after this change is merged.)

## 10. Performance baseline (cold-start)

- [x] 10.1 Added `bench/cli_cold_start.py` — subprocess-based benchmark across `py_baseline`, `import a2kit`, `cli --help`, `cli ping`, `cli hello (with DI)`, `cli ping --schema`. Reports min/median/p90 over N repeats.
- [x] 10.2 Captured baseline on local mac: see "Performance" section of the change summary.
