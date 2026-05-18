## 1. Doctrine — named misdiagnosis taxonomy (scope-tightened; see implementation log)

The originally-planned ADR + full v2 addendum was retracted on re-validation: most of the round-11 lessons (F2/F4/C2/C3 substance, A3 + E worked examples) already shipped in v0.39.2's doctrine. The one genuine gap is **named taxonomy** so future filings can pattern-match. Items 1.1 and 1.2 dropped. Items 1.3 and 1.4 retained with tighter scope.

- [x] 1.3 Add a short "Known misdiagnosis shapes" subsection to `docs/CONSUMER_FEEDBACK_DOCTRINE.md` under C3, naming **Shape A3** ("right primitive, wrong use case") and **Shape E** ("correct design mistaken for accidental ceremony") with one-paragraph descriptions and references to the existing worked examples in F2 and C2. ~15-20 LOC, no restatement of F2/C2 substance.
- [x] 1.4 Update the friction-filing template's "Misdiagnosis self-check" line in `docs/CONSUMER_FEEDBACK_DOCTRINE.md` to include an optional shape-pattern hint: "(See 'Known misdiagnosis shapes' — does this filing pattern-match Shape A3 or Shape E?)". One line. Filing template stays under one screen.

## 2. `ambient_for_tests_autouse` — implementation

- [x] 2.1 Add `ambient_for_tests_autouse` next to the existing `ambient_for_tests` definition in `src/a2kit/packages/testing/fixtures.py`. Implementation pre-decorates the same underlying fixture body with `pytest.fixture(autouse=True)` — share the implementation function, do not duplicate the body.
- [x] 2.2 Re-export `ambient_for_tests_autouse` from `src/a2kit/packages/testing/__init__.py` next to the existing `ambient_for_tests` re-export.
- [x] 2.3 Re-export `ambient_for_tests_autouse` from `src/a2kit/testing.py` so `from a2kit.testing import ambient_for_tests_autouse` works.
- [x] 2.4 Docstring on `ambient_for_tests_autouse` cross-links to the bare `ambient_for_tests` and states the one-line decision rule (project-wide → autouse variant; per-test opt-in → bare fixture).

## 3. `ambient_for_tests_autouse` — tests

- [x] 3.1 In `tests/test_testing_ambient_fixture.py`, add a scenario: bare conftest importing only `ambient_for_tests_autouse` lets a no-fixture-declaring test call `a2kit.ldd.event(...)` without raising `AmbientContextMissing`.
- [x] 3.2 Add a scenario asserting the imported `ambient_for_tests_autouse` carries the `_pytestfixturefunction` marker and that its `autouse` attribute is `True`.
- [x] 3.3 Add a regression scenario: a project that does NOT import the autouse variant still raises `AmbientContextMissing` for tests that omit the bare fixture from their signature. (Confirms strict additivity.)
- [x] 3.4 Add a scenario asserting both flavors emit no wire-side effects under their default flag values (`events_enabled=False`, `reports_enabled=False`).

## 4. OPERATIONAL_CONTRACTS update

- [x] 4.1 Update the Q-AmbientForTests entry in `OPERATIONAL_CONTRACTS.md` (or wherever it currently lives — locate via grep) to document both flavors. Add the one-line decision rule. Keep the `__wrapped__` re-export pattern documented as the pre-v0.40 shape (still valid, no migration required).

## 5. Verification

- [ ] 5.1 Run `make test` (or the project's pytest target) and confirm all tests green, including the four new scenarios.
- [ ] 5.2 Run `openspec validate a2web-feedback-round-11 --strict` and confirm clean.
- [ ] 5.3 Run any project-level lint / type-check target (e.g., `make lint`, `make ty`) and confirm clean.

## 6. Release

- [ ] 6.1 Bump version to v0.39.3 (patch — additive testing helper + docs). Use `pnpm`-equivalent / project's canonical version-bump command per `feedback_pnpm_cli` if applicable; otherwise hand-edit `pyproject.toml` only if no automation exists.
- [ ] 6.2 Update CHANGELOG with one entry per change item (autouse variant; doctrine v2).
- [ ] 6.3 Commit on `main` directly (solo repo per `feedback_no_prs`). No PR.
- [ ] 6.4 Archive the change with `openspec archive a2web-feedback-round-11` after merge.
