## 0. Prerequisites

- [x] 0.1 Reading-only spike on 2026-05-15 confirmed branch 2A: `_run_one_check` (`packages/health/__init__.py:100-114`) routes through `Container.resolve_params` → `_construct` → `_enter_lifecycle`, which calls `__aenter__`. Singleton exit happens at app shutdown via `Container.aclose()`, NOT per probe.
- [ ] 0.2 Baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov`.
- [ ] 0.3 Locate `OPERATIONAL_CONTRACTS.md` Q-numbering: read the existing tail and pick the next sequential Q.

## 1. Pinning test — `tests/test_health_check_resource_entry.py`

- [ ] 1.1 Write failing test (BDD-first) with `SpyResource` exposing `entered: int` / `exited: int` counters incremented in `__aenter__` / `__aexit__`.
- [ ] 1.2 Scenario `first_probe_enters_singleton`:
  - Register `SpyResource` via `app.singleton(SpyResource, SpyResource)`.
  - Register `@app.health_check def probe(spy: SpyResource): return a2kit.HealthResult.ok()`.
  - Build app, enter `lifespan_cm`, call `run_checks(app)` once.
  - Assert `spy.entered == 1` AND `spy.exited == 0` after `run_checks` returns (still inside lifespan).
- [ ] 1.3 Scenario `second_probe_reuses_singleton`:
  - Same setup, call `run_checks(app)` twice.
  - Assert `spy.entered == 1` (no re-entry) AND `spy.exited == 0` (still alive).
- [ ] 1.4 Scenario `singleton_exits_at_lifespan_unwind`:
  - Same setup, call `run_checks(app)` inside lifespan, exit lifespan.
  - Assert `spy.exited == 1` after lifespan exits.
- [ ] 1.5 Scenario `shared_singleton_enters_once_across_checks`:
  - Register two checks `probe_a(spy: SpyResource)` and `probe_b(spy: SpyResource)`.
  - Call `run_checks(app)` once.
  - Assert `spy.entered == 1` AND both checks observed `spy is the_same_instance`.
- [ ] 1.6 Verify all four scenarios pass without any implementation changes — this is a pinning test for existing behaviour.

## 2. Documentation

- [ ] 2.1 Add a new Q to `OPERATIONAL_CONTRACTS.md`: *"Does `@app.health_check` kwarg resolution enter resources?"*
  - Answer: yes, via `Container.resolve_params` → `_construct` → `_enter_lifecycle` (`__aenter__`).
  - Scope nuance: SINGLETON resources are entered on first resolution anywhere in the app and exit at app shutdown; SCOPED resources enter/exit per dispatch.
  - Code example: `@app.health_check def probe(sqlite: SqliteResource): ...` — `sqlite` is ready; consumers SHALL NOT call `_ensure()` or equivalents.
- [ ] 2.2 Add `CHANGELOG.md` `Unreleased` entry — verify the section header (likely "Clarified" or "Documented"; otherwise add under "Changed" with a "Documented:" prefix).
- [ ] 2.3 Cross-link from `docs/feedback-responses/v0.38-a2web-round-10.md` Friction F section: replace "spike + doc, no new API" with "documented in v0.X; consumer fix is to drop `_ensure()` calls."

## 3. Spec delta + archive prep

- [ ] 3.1 `openspec validate clarify-health-check-resource-entry --strict` — must pass.
- [ ] 3.2 Confirm no header collisions with other in-flight changes touching `health-probe`. (None as of 2026-05-15.)
- [ ] 3.3 After green CI, archive: `openspec archive clarify-health-check-resource-entry`.

## 4. Sanity / non-tasks

- [ ] 4.1 No `Resource.warm_up()` primitive. The DI resolver already enters resources via `__aenter__`.
- [ ] 4.2 No changes to the health-probe dispatch code path. Existing behaviour is correct; only documentation is missing.
- [ ] 4.3 No changes to tool-dispatch resource-entry semantics.
- [ ] 4.4 No deprecation of consumer-side `_ensure()` patterns — that's a2web's internal. The framework's job is to document its own contract clearly.
