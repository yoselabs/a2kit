## 0. Prerequisites

- [x] 0.1 Baseline gates green before this change (verified before commit c0358b1; 918 passed).
- [x] 0.2 Confirmed `a2kit.testing.peek` is the canonical sync seam.

## 1. Failing tests first (BDD)

- [x] 1.1 Created `tests/test_testing_resolve.py`.
- [x] 1.2 Scenario `test_resolve_runs_di_chain_on_first_call` — first call builds T via the registered factory; `_Inner.instances_created == 1`.
- [x] 1.3 Scenario `test_resolve_enters_resource_via_aenter` — `__aenter__` runs once on first resolve; `__aexit__` fires at lifespan close, not per resolve.
- [x] 1.4 Scenario `test_resolve_returns_cached_singleton_on_second_call` — two calls in the same lifespan return the same instance by identity.
- [x] 1.5 Scenario `test_resolve_walks_dependency_chain` — `_Outer` factory takes `_Inner`; `resolve(_Outer)` builds both; direct `resolve(_Inner)` returns the same instance the outer received.
- [x] 1.6 All scenarios initially failed on ImportError as expected.

## 2. Implementation

- [x] 2.1 Added `resolve(app_, type_)` to `src/a2kit/packages/testing/__init__.py` next to `peek`. Three-line async body wrapping `await app_.container().get(type_)`.
- [x] 2.2 Re-exported via `src/a2kit/testing.py` + `__all__`.
- [x] 2.3 Added to `a2kit.packages.testing.__all__`.
- [x] 2.4 `peek` docstring updated to point at `resolve` as the async sibling (replaces the old "use `await app.container().get(T)` directly" prose).
- [x] 2.5 All 4 tests pass; no regressions.

## 3. Spec delta

- [x] 3.1 `ADDED Requirement: Async DI resolution test seam` in
  `in-process-test-client` capability with 4 scenarios (DI chain, `__aenter__` entry, singleton cache hit, dependency chain walking).

## 4. Documentation

- [x] 4.1 `CHANGELOG.md` Unreleased: extended existing testing-helpers "Added" subsection from 2 helpers to 3 (now `lazy`, `ambient_for_tests`, `resolve`).
- [x] 4.2 `docs/feedback-responses/v0.38-a2web-round-10.md` Friction A3 rewritten with "Shipped — was over-cautious on original park" framing + migration code example. Summary table row updated.

## 5. Validate + archive + commit

- [x] 5.1 `openspec validate add-testing-resolve --strict` passes.
- [x] 5.2 Full gate green: lint, ty, 922 pytest.
- [ ] 5.3 Archive via `openspec archive add-testing-resolve -y`.
- [ ] 5.4 Commit on `main`.
