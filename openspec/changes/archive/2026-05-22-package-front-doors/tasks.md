## 1. Lint rule

- [x] 1.1 Write a failing test: a package `__init__.py` defining a class body or a logic-bearing function is flagged; one with only re-exports plus a lazy `__getattr__` / `__dir__` facade is clean.
- [x] 1.2 Implement the static rule `A2K-PKG-INIT-IMPL` (modelled on `A2K-PKG-FRONT-DOOR`, housed in `rules/importing.py`); register it in the rule table.

## 2. Split `ldd`

- [x] 2.1 Relocate `ldd/__init__.py` implementation into concern-aligned submodules: `wire.py` (line formatting), `ambient.py` (per-call state + `ldd_state_for_call`), `sinks.py` (`LddEmission` / `LddSink` / fan-out), `emission.py` (`event` / `report` / `log` + shorthands + `EventRegistry` + `_AppLdd`).
- [x] 2.2 Reduce `ldd/__init__.py` to re-exports + `__all__`.
- [x] 2.3 Add `tests/packages/ldd/test_<submodule>.py` mirrors (rename existing non-mirror test files where they map); confirm the suite still passes.

## 3. Split `context` and `health`

- [x] 3.1 Relocate `context/__init__.py` into `stderr.py`; reduce `__init__.py` to re-exports; add the `test_stderr.py` mirror.
- [x] 3.2 Relocate `health/__init__.py` into `probe.py`; reduce `__init__.py` to re-exports; add the `test_probe.py` mirror.

## 4. Split `codemode`, `connections`, `formatter`, `testing`

- [x] 4.1 Relocate `codemode/__init__.py` implementation into `transform.py`; reduce `__init__.py` to re-exports; add the `test_transform.py` mirror.
- [x] 4.2 Relocate `connections/__init__.py` `install_connections` into `install.py`; reduce `__init__.py` to re-exports; add the `test_install.py` mirror.
- [x] 4.3 Relocate `formatter/__init__.py` into `truncation.py` (`truncate` + caps) and `hint.py` (`format_response`, `_plan_for_hint`); reduce `__init__.py` to re-exports; add the `test_truncation.py` / `test_hint.py` mirrors.
- [x] 4.4 Relocate `testing/__init__.py` `lazy` / `peek` / `resolve` into `seams.py`; reduce `__init__.py` to re-exports; add the `test_seams.py` mirror.

## 5. Verification

- [x] 5.1 The new lint rule reports no findings against `src/a2kit/` after the splits.
- [x] 5.2 Full test suite green (`make test`); no consumer import broke.
- [x] 5.3 `make lint` green — `A2K-TEST-MIRROR`, `A2K-LAYER`, and the import-discipline rules all pass with the new submodules.
- [x] 5.4 `openspec validate --changes --strict` passes; the change is archive-ready.
