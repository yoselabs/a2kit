## 0. Prerequisites

- [ ] 0.1 Confirm baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov`.
- [ ] 0.2 Confirm `Lazy` shape at `src/a2kit/packages/di/_lazy.py:24` is still `TypeAlias = Callable[[], Awaitable[T]]` (no runtime class to attach `.of` to).

## 1. `a2kit.testing.lazy` constructor

- [ ] 1.1 Write the failing test first (BDD discipline): `tests/test_testing_lazy.py` with scenarios mirroring the spec — returns a zero-arg awaitable, awaiting returns the original value, identity preserved, satisfies the `Lazy[T]` type alias.
- [ ] 1.2 Implement `lazy(value)` in `src/a2kit/packages/testing/__init__.py` (or a focused `_lazy.py` if the package's `__init__.py` is at the SLOC cap). Closure over `value`; the returned thunk is `async def` and returns `value` unchanged.
- [ ] 1.3 Re-export through `src/a2kit/testing.py`: add `lazy` to the import line and to `__all__`.
- [ ] 1.4 Update `a2kit.packages.testing.__init__` `__all__` to include `lazy`.
- [ ] 1.5 Verify the test passes; `make lint` green; `ty check` green.

## 2. `a2kit.testing.ambient_for_tests` fixture

- [ ] 2.1 Write the failing test first: `tests/test_testing_ambient_fixture.py` covering — fixture is importable as `from a2kit.testing import ambient_for_tests`; using it inside a pytest test lets `a2kit.ldd.event(...)` complete without `AmbientContextMissing`; events/reports flags are False by default; **without** the fixture, the same call still raises (proves fixture is opt-in, not autouse).
- [ ] 2.2 Implement the fixture in `src/a2kit/packages/testing/_fixtures.py` (new file) as a `@pytest.fixture` wrapping `ldd_state_for_call(ctx=null_context(), events_enabled=False, reports_enabled=False)`. Yield inside the `with` block.
- [ ] 2.3 Re-export through `src/a2kit/packages/testing/__init__.py` and `src/a2kit/testing.py` (add to `__all__`).
- [ ] 2.4 Confirm pytest discovers the fixture via the standard import path (the test in 2.1 imports it directly and lists it in the test signature).
- [ ] 2.5 Verify test passes; lint + type gates green.

## 3. Documentation

- [ ] 3.1 Add a "Testing helpers" subsection to `docs/patterns/` (or wherever `null_context` / `peek` are documented today; locate via `grep -rn "a2kit.testing.peek" docs/`). One paragraph per helper plus a code sample.
- [ ] 3.2 Add a `CHANGELOG.md` `Unreleased` entry under "Added" — two bullets, link to the a2web feedback round 10 file in the body.
- [ ] 3.3 Cross-link the new helpers from `OPERATIONAL_CONTRACTS.md` Q8 (the "AmbientContextMissing & how to recover" answer) — point consumers at `ambient_for_tests` as the canonical opt-in.

## 4. Spec delta + archive prep

- [ ] 4.1 Run `openspec validate --changes --strict` — must pass.
- [ ] 4.2 Confirm `add-testing-ambient-helpers` is the only change touching `in-process-test-client` spec headers; if not, check archive order with downstream changes (see CLAUDE.md "Spec-delta authoring under multi-change waves").
- [ ] 4.3 After implementation + green CI, archive: `openspec archive add-testing-ambient-helpers`.
- [ ] 4.4 Post-archive: drop a follow-up note in a2web feedback response that A1 + A2 shipped; the consumer can delete their local `lazy_of` and autouse `_ambient_ldd` after upgrading.

## 5. Out-of-scope explicit non-tasks (sanity check)

- [ ] 5.1 No `Lazy.of` runtime attribute. (`Lazy` stays a `TypeAlias`.)
- [ ] 5.2 No `A2KIT_LDD_STRICT` env var or silent-no-op outside dispatch.
- [ ] 5.3 No autouse-by-default for `ambient_for_tests`. Consumer opts in.
- [ ] 5.4 No `resolve(app, T)`, no `Router.emits_ldd`, no `Resource.warm_up()`. Separate proposals.
