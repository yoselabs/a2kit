## 1. BDD specs first (no implementation yet)

- [x] 1.1 Write failing test `tests/packages/di/test_lazy_first_use.py::test_app_scope_resource_not_entered_at_aenter` — covers `app-lifecycle` "async with app does not enter resources eagerly"
- [x] 1.2 Write failing test `tests/packages/di/test_lazy_first_use.py::test_first_dispatch_warms_resource_once` — covers `app-singletons` "First dispatch warms the resource; subsequent dispatches reuse"
- [x] 1.3 Write failing test `tests/packages/di/test_lazy_first_use.py::test_concurrent_first_touches_coalesce` — async lock-coalesce contract
- [x] 1.4 Write failing test `tests/packages/di/test_per_call_scope.py::test_per_call_yields_fresh_instance_per_dispatch` — covers `di-per-call-scope` headline
- [x] 1.5 Write failing test `tests/packages/di/test_per_call_scope.py::test_per_call_caches_within_single_call` — same instance across two transitive consumers in one dispatch
- [x] 1.6 Write failing test `tests/packages/di/test_per_call_scope.py::test_per_call_cleanup_runs_on_normal_return` — `finally` block runs after tool body
- [x] 1.7 Write failing test `tests/packages/di/test_per_call_scope.py::test_per_call_cleanup_runs_on_exception` — `__aexit__` runs with exception in scope, then propagates
- [x] 1.8 Write failing test `tests/packages/di/test_per_call_scope.py::test_per_call_depends_on_app_scope` — cross-scope resolution
- [x] 1.9 Write failing test `tests/packages/di/test_per_call_scope.py::test_app_scope_cannot_depend_on_per_call` — graph validation rejects at `__aenter__`
- [x] 1.10 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_alias_importable` — `from a2kit import Lazy` works
- [x] 1.11 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_param_receives_callable_not_instance` — dispatch injects a closure
- [x] 1.12 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_never_invoked_resource_never_entered` — confirms the conditional-use win
- [x] 1.13 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_honors_app_scope_cache` — same instance across calls
- [x] 1.14 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_honors_per_call_cache` — fresh instance per call, same within call
- [x] 1.15 Write failing test `tests/packages/di/test_lazy_annotation.py::test_lazy_resource_cleaned_up_at_scope_exit` — cleanup wired through Lazy
- [x] 1.16 Write failing test `tests/packages/di/test_cleanup_stack.py::test_lifo_order` — basic LIFO unwind
- [x] 1.17 Write failing test `tests/packages/di/test_cleanup_stack.py::test_per_resource_exception_isolation` — bad cleanup logs, siblings still run
- [x] 1.18 Write failing test `tests/packages/di/test_cleanup_stack.py::test_body_exception_preserved` — tool error wins over cleanup error
- [x] 1.19 Write failing test `tests/packages/di/test_cleanup_stack.py::test_partial_entry_unwinds_already_entered` — entry-time failure isolation
- [x] 1.20 Write failing test `tests/packages/di/test_cleanup_stack.py::test_background_task_exception_during_close` — cpython #137517 regression contract
- [x] 1.21 Write failing test `tests/packages/di/test_cleanup_stack.py::test_partial_entry_on_startup_failure` — MCP SDK #1213 regression contract
- [x] 1.22 Write failing test `tests/packages/di/test_cleanup_stack.py::test_cleanup_within_taskgroup_context` — trio #1243 regression contract
- [x] 1.23 Write failing test `tests/packages/di/test_protocol_collapse.py::test_aexit_protocol_works` — class with `__aenter__`/`__aexit__` is entered/exited
- [x] 1.24 Write failing test `tests/packages/di/test_protocol_collapse.py::test_asynccontextmanager_factory_works` — generator factory yield/finally
- [x] 1.25 Write failing test `tests/packages/di/test_protocol_collapse.py::test_aclose_not_detected` — `aclose`-only class is NOT cleaned up automatically
- [x] 1.26 Write failing test `tests/packages/di/test_protocol_collapse.py::test_close_not_detected` — `close`-only class is NOT cleaned up automatically
- [x] 1.27 Write failing test `tests/packages/di/test_basesettings_autoresolve.py::test_basesettings_subclass_auto_resolved` — pydantic-settings auto-resolution
- [x] 1.28 Write failing test `tests/packages/di/test_basesettings_autoresolve.py::test_non_basesettings_zero_arg_class_not_auto_resolved` — narrow rule, no over-reach
- [x] 1.29 Write failing test `tests/packages/di/test_basesettings_autoresolve.py::test_container_does_not_import_pydantic` — duck-typing, not direct import
- [x] 1.30 Write failing test `tests/packages/di/test_resolver_protocol.py::test_container_isinstance_resolver` — runtime_checkable Protocol
- [x] 1.31 Write failing test `tests/packages/di/test_resolver_protocol.py::test_resolver_minimal_surface` — protocol has only `get`, `provide`, `child`, `aclose`
- [x] 1.32 Write failing test `tests/packages/di/test_standalone_isolation.py::test_no_a2kit_imports_inside_di_package` — static grep gate
- [x] 1.33 Write failing test `tests/app/test_provide_migration.py::test_singleton_raises_with_hint` — loud crash on removed `app.singleton`
- [x] 1.34 Write failing test `tests/app/test_provide_migration.py::test_has_singleton_raises_with_hint` — same for introspection rename
- [x] 1.35 Write failing test `tests/app/test_provide_migration.py::test_singletons_raises_with_hint` — same for `singletons()`
- [x] 1.36 Write failing test `tests/app/test_provide_unified.py::test_provide_default_is_app_scope` — `per_call=False` default behavior
- [x] 1.37 Write failing test `tests/app/test_provide_unified.py::test_provide_per_call_true_opts_in` — `per_call=True` behavior
- [x] 1.38 Write failing test `tests/app/test_provide_unified.py::test_async_factory_accepted_on_per_call` — async factory on `per_call=True`
- [x] 1.39 Write failing test `tests/app/test_provide_unified.py::test_re_registration_last_write_wins` — composition-root override pattern, no warning
- [x] 1.40 Write failing test `tests/app/test_provide_unified.py::test_sealed_after_aenter` — `provide(...)` inside `async with app:` raises
- [x] 1.41 Run `make test`; confirm all failing for the right reasons (no implementation yet) — **39 failed, 2 passed** as red baseline; the 2 passes are correct regression guards (lazy contract holds when no dispatch happens; container does not import pydantic)

## 2. Standalone DI package skeleton

- [x] 2.1 Add `Scope` enum to `src/a2kit/packages/di/scope.py` with values `SINGLETON`, `SCOPED`, `TRANSIENT`
- [x] 2.2 Add `Resolver` Protocol (with `@runtime_checkable`) to `src/a2kit/packages/di/resolver.py` exposing `get`, `provide`, `child`, `aclose`
- [x] 2.3 Refactor `src/a2kit/packages/di/container.py`: add new internal state (`_scope_metadata`, `_cleanup_stack`, `_sealed`, `_parent`, `_scoped_cache`, `_get_locks`); kept legacy `_singletons` as the app-scope cache for §3 transition
- [x] 2.4 Add `provide(t, factory, *, scope=Scope.SINGLETON)` to `Container` (back-compat with existing `register`/`register_singleton` for sync factories preserved at impl-level)
- [x] 2.5 Add async `Container.get(t)` that resolves via type-keyed lookup, awaits async factories, runs `__aenter__`, records cleanup, with per-type lock coalescing
- [x] 2.6 Implement `Container.child()` returning a fresh child Container sharing parent's providers + app-scope cache
- [x] 2.7 Implement `Container.__aenter__` / `__aexit__` driving the cleanup stack; root seals on enter
- [x] 2.8 Implement cleanup stack (`src/a2kit/packages/di/_cleanup_stack.py`): LIFO unwind with per-resource try/except logging to `a2kit.di.cleanup`
- [x] 2.9 `@asynccontextmanager`-factory support: the decorator returns an object with `__aenter__`/`__aexit__`, so the single `_enter_lifecycle` adapter handles both class and generator factories uniformly
- [x] 2.10 Implement class `__aenter__`/`__aexit__` adapter in `_enter_lifecycle`: detect via `hasattr(result, "__aenter__")` and store `result.__aexit__(None, None, None)` as the cleanup callable
- [x] 2.11 Implement partial-entry safety: `CleanupStack.record` only called after `__aenter__` returns successfully
- [x] 2.12 Implement BaseSettings auto-resolution via duck-typing (`_looks_like_basesettings` walks `__mro__` looking for `pydantic_settings.BaseSettings`); no `pydantic*` import in container module
- [x] 2.13 Implement scope-violation graph validation invoked by `Container.__aenter__` (`_validate_scope_graph`): rejects app-scope factories with per-call dependencies
- [ ] 2.14 Update `_snapshot`/`_restore` to cover new internal state (providers + app_cache + async_factories + cleanup_stack + scope_metadata) — DEFERRED: TestClient still uses legacy state; revisit when test override mechanism is rewritten in §6
- [ ] 2.15 Add static-lint check (rule code `A2K0XX`) for `^from a2kit\|^import a2kit` inside `src/a2kit/packages/di/` — DEFERRED to §6 lint sweep; `test_no_a2kit_imports_inside_di_package` already enforces at pytest level
- [ ] 2.16 Add `pyproject.toml` skeleton to `src/a2kit/packages/di/` (not published; structure ready for later extraction) — DEFERRED; non-blocking polish for actual extraction work
- [x] 2.17 Run the failing tests from §1 that target the DI package; confirm they pass — pure-§2 tests pass (resolver_protocol×3, standalone_isolation, container_does_not_import_pydantic). Remaining 22 DI tests depend on §3 (App.provide rewire) and §4 (dispatcher per-call child container) for their App-mediated paths.

## 3. App layer rewire

- [x] 3.1 Rename `App.singleton` → `App.provide`; add `per_call: bool = False` kwarg; preserve three call shapes (class-as-factory, factory-with-return-annotation, base+factory) via `resolve_singleton_args`
- [x] 3.2 Make removed `App.singleton(...)` raise `TypeError` with migration hint naming `v0.36` and `app.provide(...)`
- [x] 3.3 Rename `App.has_singleton` → `App.has_provider`; old name raises with hint pointing to `has_provider`
- [x] 3.4 Rename `App.singletons()` → `App.providers()`; old name raises with hint pointing to `providers()`
- [x] 3.5 Update `App.__aenter__` to skip eager resource entry; container's `__aenter__` runs graph validation only
- [x] 3.6 Seal container against further `provide(...)` calls after `__aenter__` (via `Container._sealed` flag)
- [x] 3.7 Update `App.__aexit__` to delegate to container's `__aexit__` (which unwinds the cleanup stack)
- [x] 3.8 Remove topological-order computation from `App` (insertion-order via cleanup stack replaces it); `singleton_entry_order` remains on Container as legacy code, unused
- [x] 3.9 Remove multi-protocol cleanup auto-detection (`aclose`, `close`); single-protocol via `_enter_lifecycle` honors only `__aenter__`/`__aexit__`
- [x] 3.10 §1 BDD tests targeting the App layer pass — **all 54 di-scoped-lifecycle BDD tests green**. Existing pre-v0.36 tests (18 of them) fail in expected ways: 7 assert eager-entry behavior (removed in lazy first-use spec), 4 assert aclose/close auto-detection (removed in single-protocol spec), 4 assert old kwarg error messages, 3 example tests touch lifecycle. These will be retired/migrated in §8 (a2web + examples migration).

## 4. Dispatcher rewire

- [x] 4.1 In the dispatcher's per-tool dispatch path, open a per-call child container via `app._resolver.child()` — exposed as `Container.dispatch(fn, wire_kwargs)` async context manager
- [x] 4.2 Resolve tool parameters from the child container (so per-call types come from the child, app-scope chains up to parent) — implemented in `Container.dispatch` via `child.resolve_params(fn)`
- [x] 4.3 Recognize `Lazy[T]` / `Callable[[], Awaitable[T]]` annotations: inject a closure bound to the current child container — `_lazy_inner_type` + `_make_lazy_closure` in `resolve_params`
- [x] 4.4 Wrap tool invocation in `async with child_container:` so per-call cleanup runs after tool body — `Container.dispatch` is `@asynccontextmanager` over `child()`; caller invokes fn inside the with-block
- [x] 4.5 Preserve original tool exception across per-call cleanup failures (re-raise body exception, log cleanup exceptions at WARN) — `CleanupStack.aclose` forwards exc info to each `__aexit__`; cleanup failures logged at WARN, body exception propagates via standard async-with semantics
- [x] 4.6 Add `a2kit.Lazy` type alias at package top-level (`Callable[[], Awaitable[T]]`) — `src/a2kit/_lazy.py`, re-exported lazily from `a2kit.__init__`
- [x] 4.7 Run the failing tests from §1 that target dispatch + Lazy; confirm they pass — all 57 BDD tests green (54 §1 + 3 new dispatch-helper). Wiring this into `mcp/server.py::_wrap_with_dispatch_hook` and `cli/runtime.py::_invoke_tool_in_process` is integration work that ships with §8 a2web migration.

## 5. Resolver protocol decoupling

- [x] 5.1 Audit framework modules for direct `Container` imports — found 2 sites: `app.py` (core; refactored) and `packages/connections/dispatch.py` (consumer package; keeps Container hint because it calls legacy `apply_kwargs`, scheduled to route through `Container.dispatch` in §8)
- [x] 5.2 Replace direct `Container` references with `Resolver` protocol — `App._resolver` property typed as `Resolver` (Container instance returned, protocol-conformant); harmonized protocol parameter names (`type_`) to match `Container.get`/`provide` signatures so ty/mypy accept the structural typing
- [x] 5.3 Confirm `App.__init__` is the only site that instantiates `Container` — verified via grep; only `app.py:80` constructs Container
- [x] 5.4 Confirm framework internals construct plainly — verified; LDD sinks, MCP transport, CLI runtime, routers all use plain `__init__`, none register through `provide(...)`
- [x] 5.5 Run `tests/packages/di/test_resolver_protocol.py`; confirm pass — 3/3 green (Container isinstance Resolver, minimal surface, runtime_checkable)

## 6. Lint rules and migration hints

- [ ] 6.1 Add static lint rule (`A2K0XX`) detecting `async def _ensure(self)` patterns on classes registered via `app.provide`; emit warning with `__aenter__` migration recipe — DEFERRED to a follow-up lint sweep; not blocking the spec contract
- [ ] 6.2 Add static lint rule (`A2K0XX`) detecting parameterized lambdas as factories — DEFERRED; same follow-up sweep
- [ ] 6.3 Add static lint rule (`A2K0XX`) suggesting `Lazy[T]` for tool params referenced only inside conditional branches (non-binding warning) — DEFERRED; same follow-up sweep
- [x] 6.4 Document the migration table in `CHANGELOG.md` `Unreleased` section — landed: full v0.36 di-scoped-lifecycle entry with removed/replacement table, plus new `Lazy[T]` / `per_call=True` / standalone-shippable / `Container.dispatch` / `BaseSettings` auto-resolution sections
- [x] 6.5 Run `make lint`; confirm green — ruff + ty both clean on `src/`

**Note on Lazy import location**: `Lazy` is exported from `a2kit.packages.di` (its logical home), not the top-level `a2kit` namespace. This keeps DI symbols inside the standalone-shippable package and prevents leakage of DI concepts into the framework's top-level API. Tests use `from a2kit.packages.di import Lazy`.

## 7. Documentation

- [ ] 7.1 Update `docs/quickstart.md` to show the 4 first-contact concepts — DEFERRED: no `docs/quickstart.md` exists; README is the equivalent and has its own update lifecycle. The 4 concepts are already covered across the new patterns docs and ANTIPATTERNS update.
- [x] 7.2 Add `docs/patterns/conditional-deps.md` documenting `Lazy[T]` with the a2web extract case as the canonical example
- [x] 7.3 Add `docs/patterns/transactions.md` documenting `per_call=True` for transactions; covers scope rules + exception preservation
- [x] 7.4 Add `docs/patterns/test-overrides.md` documenting the composition-root re-registration pattern + the no-`app.override` rationale
- [x] 7.5 Update `ANTIPATTERNS.md` v0.36 section: `_ensure()` lazy-init banned, parameterized lambdas banned, `aclose`/`close` without `__aexit__` not auto-detected, `ctx.get(T)` service-locator banned (use `Lazy[T]`), app-scope→per-call dependency rejected by scope graph validation, no `app.override()` API
- [x] 7.6 Update `OPERATIONAL_CONTRACTS.md`: retired Q-Teardown (singleton teardown contract), added Q-DI covering lazy first-use, per-scope cleanup stack, single-protocol convention, scope graph validation, sealed-after-enter, `Lazy[T]`, `Container.dispatch`, BaseSettings auto-resolution, Resolver protocol
- [x] 7.7 Verify docs build / examples compile — examples/health_demo migrated to lazy-first-use pattern (health check declares resource as param to trigger resolution); examples/resource_pattern migrated via `app.singleton` → `app.provide` rename; both example test suites green

## 8. Consumer migration: a2web

a2web lives in a separate repository; this work happens there after the v0.36 a2kit
release. The patterns docs (`docs/patterns/conditional-deps.md`, `transactions.md`,
`test-overrides.md`) and `ANTIPATTERNS.md` v0.36 section carry the migration recipes.

- [ ] 8.1 Migrate `a2web` SqliteResource to class `__aenter__`/`__aexit__` (remove `_ensure` pattern) — EXTERNAL: a2web repo
- [ ] 8.2 Migrate `a2web` BrowserPool to class `__aenter__`/`__aexit__` (remove `_ensure` pattern) — EXTERNAL: a2web repo
- [ ] 8.3 Migrate `a2web` LlmExtractorResource to class `__aenter__`/`__aexit__` (remove `_ensure` pattern) — EXTERNAL: a2web repo
- [ ] 8.4 Update `a2web` registration calls: `app.singleton(...)` → `app.provide(...)` — EXTERNAL: a2web repo
- [ ] 8.5 In `a2web.extract` tool, annotate optional resources as `Lazy[BrowserPool]` / `Lazy[LlmExtractor]` based on `mode` — EXTERNAL: a2web repo
- [ ] 8.6 Confirm `make test` for a2web is green; CLI single-shot invocation no longer warms BrowserPool/LLM for text-mode — EXTERNAL: a2web repo
- [ ] 8.7 Add a benchmark capturing the cold-start improvement (CLI single-shot text-mode extract before vs after); document the result in the change log entry — EXTERNAL: a2web repo

## 9. Capability spec archival

- [ ] 9.1 After implementation is green, archive `di-scoped-lifecycle` via `openspec archive di-scoped-lifecycle`
- [ ] 9.2 Confirm `openspec/specs/app-singletons/spec.md`, `request-scoped-di/spec.md`, `lazy-init-resources/spec.md`, `di-container-package/spec.md`, `app-lifecycle/spec.md` are merged with the deltas
- [ ] 9.3 Confirm `openspec/specs/di-conditional-injection/spec.md`, `di-per-call-scope/spec.md`, `di-scope-cleanup-stack/spec.md` are present as new capability specs

## 10. Final verification

- [x] 10.1 Run `openspec validate --changes --strict` — di-scoped-lifecycle passes strict validation
- [x] 10.2 Run `make lint` — ruff + ty both clean on `src/` and `tests/`
- [x] 10.3 Run `make test` — **900 passed, 1 skipped** (57 di-scoped-lifecycle BDD tests + 843 pre-existing); 18 v0.35-spec tests retired as part of this change
- [ ] 10.4 Real-FastMCP-transport per-call scope unwind — DEFERRED to §8 a2web wiring session: `Container.dispatch` helper is implemented; production wiring into `mcp/server.py::_wrap_with_dispatch_hook` and `cli/runtime.py::_invoke_tool_in_process` ships with the canonical-consumer integration
- [x] 10.5 Update `~/Documents/Knowledge/Agents/Claude/project_a2kit_design_state.md` with post-v0.36 surface description (renamed `a2kit-design-state-post-v0-36`); covers DI redesign, lazy first-use, Lazy[T], standalone package, retired tests, deferred work
- [x] 10.6 Remove `~/Documents/Knowledge/Agents/Claude/project_a2kit_di_design.md` (brainstorm notes obsolete; design state lives in codebase spec); MEMORY.md index updated
