## 1. Container snapshot/restore

- [ ] 1.1 Add `_snapshot()` and `_restore(snapshot)` to `a2kit.packages.di.container.Container`; shallow-copy `_providers` and `_singletons` into an opaque dataclass/tuple
- [ ] 1.2 Write a unit test for `_snapshot()`/`_restore()` covering provider mutation, singleton mutation, and round-trip identity
- [ ] 1.3 Verify the hot-path `Container.resolve` is unchanged (no new branches); add a grep-style test asserting the source has no `_overrides` symbol

## 2. TestClient.override

- [ ] 2.1 Add `TestClient.override(type_: type[T], fake: T) -> None` in `src/a2kit/packages/testing/client.py`, with a `TypeVar("T")` for type safety
- [ ] 2.2 On first `override` call per session, capture `self._snapshot = app.container()._snapshot()`; pin both `_singletons[T] = fake` and `_providers[T] = lambda: fake`
- [ ] 2.3 In `__aexit__`, if `self._snapshot is not None`, call `app.container()._restore(self._snapshot)` and clear the override-owner flag on the App
- [ ] 2.4 Add a session-ownership flag on `App` (`_test_override_owner`) and raise `RuntimeError` from `override(...)` when another TestClient already holds it
- [ ] 2.5 Ensure `__aexit__` clears the snapshot and owner flag on both normal and exceptional exit (test both paths)

## 3. Tests against the spec scenarios

- [ ] 3.1 Test: override replaces a singleton-registered dependency (resolved + peek both return the fake)
- [ ] 3.2 Test: override replaces a per-call provider-registered dependency across multiple `invoke(...)` calls
- [ ] 3.3 Test: override is restored on normal exit (`peek` after the block returns the original)
- [ ] 3.4 Test: override is restored on exceptional exit (raise inside `invoke`, assert restoration)
- [ ] 3.5 Test: override of an unregistered type registers fresh, then is removed on exit
- [ ] 3.6 Test: last-write-wins within a session, exit restores to pre-session state
- [ ] 3.7 Test: concurrent TestClient override on the same App raises `RuntimeError`
- [ ] 3.8 Type-check fixture (pyright/ty): asserts that `c.override(LLMExtractor, "string")` produces an argument-type error without `# type: ignore`

## 4. Documentation and consumer migration

- [ ] 4.1 Add an "Overriding dependencies in tests" subsection to the testing README/docs showing the canonical `c.override(T, fake)` pattern next to the obsolete `monkeypatch.setattr(...)` pattern
- [ ] 4.2 Update `a2kit.testing.__init__` if needed so `override` shows up in `dir(TestClient)` and IDE auto-complete
- [ ] 4.3 Cross-reference `peek` ↔ `override` in both docstrings (read-side / write-side complement)

## 5. Validation

- [ ] 5.1 `openspec validate testing-di-override --strict` passes
- [ ] 5.2 Full test suite passes locally (`make test` or equivalent)
- [ ] 5.3 Type-check passes with zero new `# type: ignore` introduced
