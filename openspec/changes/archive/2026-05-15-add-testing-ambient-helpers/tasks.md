## 0. Prerequisites

- [x] 0.1 Baseline green before this change.
- [x] 0.2 `Lazy` shape at `src/a2kit/packages/di/_lazy.py:24` confirmed as `TypeAlias = Callable[[], Awaitable[T]]`.

## 1. `a2kit.testing.lazy` constructor

- [x] 1.1 Failing test written: `tests/test_testing_lazy.py` (5 scenarios — zero-arg async callable, identity preserved, Lazy[T] shape, None value, complex value).
- [x] 1.2 Implemented `lazy(value)` in `src/a2kit/packages/testing/__init__.py` as a closure factory.
- [x] 1.3 Re-exported through `src/a2kit/testing.py` + `__all__`.
- [x] 1.4 Added to `a2kit.packages.testing.__init__` `__all__`.
- [x] 1.5 Tests pass; lint + ty green.

## 2. `a2kit.testing.ambient_for_tests` fixture

- [x] 2.1 Failing test written: `tests/test_testing_ambient_fixture.py` (4 scenarios — importability, ambient enables event emission, absence raises Mode A, default flags don't break flow).
- [x] 2.2 Implemented the fixture in `src/a2kit/packages/testing/fixtures.py` (folded into the existing fixtures module rather than a separate file, matching the existing `app`/`cassette` pattern).
- [x] 2.3 Re-exported through `__init__.py` and `testing.py` `__all__`.
- [x] 2.4 Pytest discovers via standard import path (test in 2.1 uses it as a fixture parameter — collection succeeds).
- [x] 2.5 Tests pass.

## 3. Documentation

- [x] 3.1 `OPERATIONAL_CONTRACTS.md` Q8 cross-linked the canonical opt-in path (existing prose, no new docs/patterns/ section needed).
- [x] 3.2 `CHANGELOG.md` Unreleased "Added" entry shipped.
- [x] 3.3 OPERATIONAL_CONTRACTS Q8 updated.

## 4. Spec delta + archive prep

- [x] 4.1 `openspec validate --changes --strict` passed.
- [x] 4.2 No header collisions with other in-flight changes.
- [ ] 4.3 Archive: `openspec archive add-testing-ambient-helpers -y`.
- [x] 4.4 Followup: response doc updated post-archive.

## 5. Out-of-scope explicit non-tasks (sanity check)

- [x] 5.1 No `Lazy.of` runtime attribute. (`Lazy` stays a `TypeAlias`.)
- [x] 5.2 No `A2KIT_LDD_STRICT` env var or silent-no-op outside dispatch.
- [x] 5.3 No autouse-by-default for `ambient_for_tests`. Consumer opts in.
- [x] 5.4 No `resolve(app, T)`, no `Router.emits_ldd`, no `Resource.warm_up()`. Separate proposals.
