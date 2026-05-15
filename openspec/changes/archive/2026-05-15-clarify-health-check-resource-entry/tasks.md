## 0. Prerequisites

- [x] 0.1 Reading-only spike on 2026-05-15 confirmed branch 2A: `_run_one_check` (`packages/health/__init__.py:100-114`) routes through `Container.resolve_params` → `_construct` → `_enter_lifecycle`, which calls `__aenter__`. Singleton exit happens at app shutdown via `Container.aclose()`, NOT per probe.
- [x] 0.2 Baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov` — verified before commit 5752694 (908 passed).
- [x] 0.3 OPERATIONAL_CONTRACTS Q-numbering: named-Q convention (Q-Ctx, Q-DI) — new Q named `Q-HealthChecks`, inserted after Q-DI before "See also".

## 1. Pinning test — `tests/test_health_check_resource_entry.py`

- [x] 1.1 `SpyResource` class with `entered`/`exited` counters in `__aenter__`/`__aexit__`.
- [x] 1.2 Scenario `test_first_probe_enters_singleton`: asserts `spy.entered == 1` at body-run-time and `spy.exited == 0` while lifespan in flight.
- [x] 1.3 Scenario `test_second_probe_reuses_cached_singleton`: two invocations, `entered == 1` (no re-entry).
- [x] 1.4 Scenario `test_singleton_exits_at_lifespan_unwind`: `exited == 1` after `async with client(app)` block exits.
- [x] 1.5 Scenario `test_shared_singleton_across_checks_enters_once`: two distinct checks, both see same instance by `id()`.
- [x] 1.6 Additional scenario `test_run_checks_directly_enters_singleton`: lower-level `run_checks(app)` API (CLI path) also enters via resolver.
- [x] 1.7 All 5 scenarios pass; behaviour pinning confirmed (no implementation changes needed — contract was already in place).

## 2. Documentation

- [x] 2.1 New Q `Q-HealthChecks` added to `OPERATIONAL_CONTRACTS.md` between Q-DI and "See also". Covers: resolution path, singleton vs per-call scope nuance, code example with explicit "do not call internal `_ensure()`" guidance, cross-link to pinning test.
- [x] 2.2 `CHANGELOG.md` Unreleased "Clarified" subsection added documenting the contract promotion + singleton nuance + explicit rejection of `Resource.warm_up()`.
- [ ] 2.3 Cross-link from `docs/feedback-responses/v0.38-a2web-round-10.md` Friction F section. (Bundled into the same commit; the response doc Friction F already documents the spike outcome — see lines 189-232. Will update to point at the shipped Q after archive.)

## 3. Spec delta + archive prep

- [x] 3.1 `openspec validate clarify-health-check-resource-entry --strict` — passes.
- [x] 3.2 No header collisions with other in-flight changes touching `health-probe`.
- [ ] 3.3 Archive: `openspec archive clarify-health-check-resource-entry -y`.

## 4. Sanity / non-tasks

- [x] 4.1 No `Resource.warm_up()` primitive added.
- [x] 4.2 No changes to the health-probe dispatch code path.
- [x] 4.3 No changes to tool-dispatch resource-entry semantics.
- [x] 4.4 No deprecation of consumer-side `_ensure()` patterns.
