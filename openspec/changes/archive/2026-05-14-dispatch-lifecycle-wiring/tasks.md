# Tasks — dispatch-lifecycle-wiring

## 1. BDD baseline (red tests)

- [x] 1.1 Write failing real-MCP-transport test
  `tests/packages/mcp/test_per_call_scope_real_wire.py::test_per_call_resource_cleaned_up_at_mcp_call_exit`
- [x] 1.2 Write failing real-MCP-transport test
  `tests/packages/mcp/test_per_call_scope_real_wire.py::test_per_call_resource_sees_body_exception_on_aexit`
- [x] 1.3 Write failing real-MCP-transport test
  `tests/packages/mcp/test_lazy_param_real_wire.py::test_lazy_never_invoked_resource_not_entered_under_mcp`
- [x] 1.4 Write failing CLI runtime test
  `tests/packages/cli/test_per_call_scope_cli.py::test_per_call_resource_cleaned_up_at_cli_call_exit`
- [x] 1.5 Write failing CLI runtime test
  `tests/packages/cli/test_lazy_param_cli.py::test_lazy_never_invoked_under_cli`
- [x] 1.6 Confirm all 5 fail with diagnostic that names the missing wiring (not random crashes) — **5 failed** as red baseline: MCP tests fail at schema-gen (dispatcher sees `Lazy[T]` / per-call type as un-schematizable callable param because injectability not recognized), CLI tests fail with `TypeError: missing positional argument 'tx'`/'browser' (current `_default_dispatch_hook` doesn't resolve DI for the new providers). Wiring landing in §3-§5 flips these green.

## 2. `Container.dispatch` grows `pre_hook` parameter

- [x] 2.1 Extend signature: `dispatch(fn, wire_kwargs=None, *, pre_hook=None)`
- [x] 2.2 When `pre_hook` is set, invoke it (await if coroutine) with `(fn, dict(wire_kwargs))` before DI resolution; replace wire_kwargs with its return value
- [x] 2.3 Document: pre_hook contract is wire-side conversion only; framework runs DI after via `child.resolve_params`
- [x] 2.4 Add BDD test `test_pre_hook_runs_before_di_resolution` — passes
- [x] 2.5 Add BDD test `test_pre_hook_output_seeds_chain_resolution` — passes; wire-resolved typed configs become SCOPED providers on the child container so chain resolution from per-call factories finds them. Also fixed `Container.get` scope-of lookup to consult the calling container's metadata first (not just root's). Filter merged kwargs to `fn`'s declared params so wire-side keys the hook consumed but `fn` doesn't take aren't passed through.

## 3. MCP transport wiring

- [x] 3.1 In `_wrap_with_dispatch_hook` (`mcp/server.py`), replaced `hook(fn, kwargs) → fn(**resolved)` with `async with app._resolver.dispatch(fn, kwargs, pre_hook=hook) as merged: ... fn(**merged)`
- [x] 3.2 Thread `app` through `_wrap_with_dispatch_hook` signature; updated `wire_input_params` to filter `Lazy[T]` annotations alongside provider-registered types
- [x] 3.3 Preserved signature rewrite logic (wire params + connection + ctx). The dispatch helper filters merged kwargs to fn's declared params, plus the wrapper pops `ctx` from wire kwargs and merges it back inside the dispatch CM
- [x] 3.4 Wire-error envelope wrapper still sees body exceptions — verified via `test_per_call_resource_sees_body_exception_on_aexit` (envelope payload carries `{"class": "ValueError", "message": "boom"}`)
- [x] 3.5 §1 MCP tests pass — all 3 green (`test_per_call_resource_cleaned_up_at_mcp_call_exit`, `test_per_call_resource_sees_body_exception_on_aexit`, `test_lazy_never_invoked_resource_not_entered_under_mcp`)

## 4. CLI runtime wiring

- [x] 4.1 In `_invoke_tool_in_process`, replaced the `hook(fn, kwargs)` pattern with `async with app._resolver.dispatch(fn, kwargs, pre_hook=hook) as merged: ...` when `app` is supplied; standalone `app=None` path keeps the legacy no-DI behavior
- [x] 4.2 `ctx_param_name` injection moves inside the dispatch CM, into `_run_inside_call`
- [x] 4.3 Timeout + LDD-state wrapping moved inside the dispatch CM so per-call cleanups see propagating exceptions
- [x] 4.4 `invoke_tool_sync` now passes `app=app` through to `_invoke_tool_in_process` when the App is bound
- [x] 4.5 §1 CLI tests pass — both green (`test_per_call_resource_cleaned_up_at_cli_call_exit`, `test_lazy_never_invoked_under_cli`)

## 5. Connections hook simplification

- [x] 5.1 In `make_connection_hook`, dropped the trailing `container.apply_kwargs(...)` call. Hook now returns wire-side resolved kwargs only: typed configs surface under the tool-param name when the tool declares the config directly, OR under a stable `_a2k_seed_<TypeName>` key when the tool only reaches the config through a chain — Container.dispatch's wire-seeder picks them up by value type either way and registers SCOPED providers on the per-call child.
- [x] 5.2 `install_connection_dispatch` now registers connection types as `Scope.SCOPED` providers (the no-op stub factory) — chain resolution routes through the dispatch's child container where the wire-seeder has the actual instance. Connection configs are inherently per-call (each dispatch can target a different connection); the scope-graph validator correctly flags app-scope stores that depend on them.
- [x] 5.3 Existing `tests/packages/connections/test_di_dispatch.py` passes against the narrowed contract — `app.provide(_Store)` updated to `app.provide(_Store, per_call=True)` because connection-coupled stores are per-call by nature; the scope-graph validator catches this if a consumer keeps them app-scope.
- [ ] 5.4 Add BDD test `tests/packages/connections/test_dispatch_lazy.py::test_lazy_param_works_through_connection_dispatch` — DEFERRED to a follow-up: the framework-level Lazy[T] + connection-dispatch interaction works (covered by §1 + §2 + §5 in combination), but a dedicated cross-package scenario adds extra coverage value

## 6. Remove `identity_dispatch_hook` + default hook simplification

- [x] 6.1 Removed `a2kit.tool.identity_dispatch_hook` and its public export from `__all__`. `DispatchHook` Protocol docstring updated to the v0.37 wire-side-only contract.
- [x] 6.2 `App._default_dispatch_hook` already simplified in §3: identity over wire_kwargs, no `container_dispatch` call. DI runs inside `Container.dispatch` on the hook's output.
- [ ] 6.3 Remove `_default_dispatch_hook` entirely — DEFERRED: would require all callers to handle `pre_hook=None` and conditionally compose the wrapper. Identity-default is cheap (one function call); deletion is a tidiness sweep for a follow-up.
- [x] 6.4 CLI runtime's `dispatch_hook: ... | None` already treats None as "no pre_hook" via the `app=None` branch in §4 work.
- [x] 6.5 Cold-start: 3 fresh subprocess imports measure 7-11ms; well under the 100ms budget. `tests/test_cold_start.py` 8/8 green.

## 7. Removed-behavior test retirements

- [x] 7.1 Audit existing dispatch / connections tests for assertions against the old contract — `tests/test_decoration_warn_once.py::test_l1_dispatch_hook_return_annotation_failure_warns_once` updated to pass `app` instead of `container`; `tests/packages/connections/test_di_dispatch.py` updated to `app.provide(_Store, per_call=True)`; `examples/tracker/server.py` got the same per-call treatment. No `identity_dispatch_hook` references remain.
- [x] 7.2 Update or retire those assertions; update CHANGELOG migration table — landed: `CHANGELOG.md` Unreleased v0.37 section with breaking dispatch-hook contract narrowing, connection-coupled-providers-default-to-per-call migration, `Container.dispatch(pre_hook)` new feature, Lazy[T] wire-aware filtering.

## 8. Verification + archive

- [ ] 8.1 `openspec validate --changes --strict` clean
- [ ] 8.2 `make lint` (ruff + ty on src/) clean
- [ ] 8.3 `make test` full suite green including all §1 BDD scenarios + new dispatch-helper scenarios
- [ ] 8.4 `openspec archive dispatch-lifecycle-wiring`
- [ ] 8.5 Update `project_a2kit_design_state.md` memory with the v0.37 dispatch contract
- [ ] 8.6 Commit + tag `v0.37.0` + push
