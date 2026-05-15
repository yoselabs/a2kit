## 0. Prerequisites

- [x] 0.1 Baseline gates green before changes (verified before commit efcfa03; 913 passed).
- [x] 0.2 Confirmed `_construct_kwargs` did not branch on `_lazy_inner_type(ann)` (read at `packages/di/container.py:539-554` during explore mode).
- [x] 0.3 `_lazy_inner_type` is imported at `container.py:43` and used by `resolve_params` line 433.

## 1. Failing tests first (BDD per `feedback_bdd_first`)

- [x] 1.1 Created `tests/packages/di/test_lazy_in_factory_params.py`.
- [x] 1.2 Scenario `test_singleton_factory_with_lazy_app_scope_t_works` — factory takes `Lazy[_Inner]` where `_Inner` is app-scope; tool body awaits the captured thunk; `_Inner.entered == 1` after await, `instances_created == 1`.
- [x] 1.3 Scenario `test_singleton_factory_lazy_handle_never_awaited` — tool body never calls the thunk; `_Inner.instances_created == 0`, `_Inner.entered == 0`.
- [x] 1.4 Scenario `test_singleton_factory_with_lazy_per_call_rejected` — `Lazy[_PerCallThing]` in SINGLETON factory; `async with app:` raises `TypeError` naming the per-call type, the `Lazy[]` shape, and the migration hint.
- [x] 1.5 Scenario `test_per_call_factory_with_lazy_t_works` — per-call factory with `Lazy[_Inner]` (Inner app-scope); two dispatches yield fresh aggregates, same Inner (`Inner.entered == 1`).
- [x] 1.6 Bonus scenario `test_singleton_factory_lazy_handle_cached_across_dispatches` — pins app-scope caching semantics across two dispatches.
- [x] 1.7 All scenarios initially failed in the expected ways (UnresolvableType for 1.2/1.3/1.5/1.6, DID NOT RAISE for 1.4).

## 2. Implementation

- [x] 2.1 `_construct_kwargs` in `packages/di/container.py` gained the `Lazy[T]` branch mirroring `resolve_params` — 6 lines, inserted before the `has_provider` check.
- [x] 2.2 `_validate_scope_graph` gained a mirror clause: SINGLETON factory + `Lazy[T]` where T is SCOPED → `TypeError` with migration hint naming the inner type and both fix paths (move inner to app-scope, or make outer factory per-call).
- [x] 2.3 All 5 tests pass after both changes; no regressions in the wider DI suite.

## 3. Spec delta

- [x] 3.1 `MODIFIED` requirement (existing `Lazy[T] is a type alias for deferred resolution`) — added two new scenarios covering factory-param recognition + lazy-never-awaited cleanup invariant.
- [x] 3.2 `ADDED` requirement (`SINGLETON factories may not declare Lazy[per-call-type] parameters`) — three scenarios: rejected case, app-scope inner accepted, per-call outer accepted.

## 4. Documentation

- [x] 4.1 `CHANGELOG.md` Unreleased: new "Fixed" subsection describing the spec-impl drift closure + scope-graph guard.
- [x] 4.2 `OPERATIONAL_CONTRACTS.md` Q-DI: `Lazy[T]` paragraph updated to mention factory-param support + the scope-graph guard with migration hint.
- [x] 4.3 `docs/feedback-responses/v0.38-a2web-round-10.md` Friction E: replaced "park, leaning reject" with the corrected verdict (Interpretation A rejected, Interpretation B shipped). Updated summary table row.

## 5. Validate + archive

- [x] 5.1 `openspec validate lazy-in-factory-params --strict` passes.
- [x] 5.2 Full gate green: `make lint`, `uv run ty check src/`, 918 pytest.
- [ ] 5.3 Archive via `openspec archive lazy-in-factory-params -y`.

## 6. Sanity / non-tasks

- [x] 6.1 No attribute-side-effects implementation (Interpretation A stays rejected).
- [x] 6.2 No changes to tool dispatch (`resolve_params`) — already correct.
- [x] 6.3 No new top-level surface; `Lazy` annotation unchanged.
- [x] 6.4 No silent migration — rejected case raises `TypeError` at app entry with a clear hint.
