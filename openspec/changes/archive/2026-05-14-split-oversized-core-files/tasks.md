# Tasks — split oversized core files

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` + `make lint` green.
- [x] 0.2 Record current SLOC:
      ```
      uv run python -c "
      import pathlib
      for p in ['src/a2kit/packages/di/container.py', 'src/a2kit/tool.py']:
          lines = pathlib.Path(p).read_text().splitlines()
          sloc = sum(1 for l in lines if l.strip() and not l.strip().startswith('#'))
          print(f'  {p}: {sloc}')"
      ```
      Expect ~567 (container.py) and ~537 (tool.py).

## 1. Split container.py → container.py + teardown.py

- [x] 1.1 Create `src/a2kit/packages/di/teardown.py`. Export:
      - `_build_teardown_edges(candidates: ...) -> dict[type, set[type]]`
      - `teardown_order(providers, teardowns) -> list[type]` (Kahn's
        algorithm with cycle-break + WARN)
      - Module-level logger `_log = logging.getLogger(__name__)`
- [x] 1.2 Move the implementations from `container.py` into
      `teardown.py`. Preserve docstrings.
- [x] 1.3 In `container.py`:
      ```python
      from a2kit.packages.di.teardown import teardown_order as _teardown_order
      ```
      Replace `Container.teardown_order` body with `return
      _teardown_order(self._providers, self._teardowns)` or similar
      thin delegation.
- [x] 1.4 Sweep tests/ for any imports of `_build_teardown_edges`
      or internal teardown helpers from `container`. Likely zero;
      update if any.
- [x] 1.5 Remove `# noqa: A2K014` from `container.py:1`.
- [x] 1.6 Verify SLOC drops below 500:
      `wc -l src/a2kit/packages/di/container.py`.

## 2. Split tool.py → tool.py + _timeout.py

- [x] 2.1 Create `src/a2kit/_timeout.py`. Export:
      - `_parse_timeout(value: float | int | str | None) -> float | None`
      - any timeout-related constants (suffix multipliers, etc.)
- [x] 2.2 Move the `_parse_timeout` implementation from `tool.py`
      into `_timeout.py`. Preserve docstring.
- [x] 2.3 In `tool.py`, replace the local `_parse_timeout` definition
      with `from a2kit._timeout import _parse_timeout`.
- [x] 2.4 Sweep tests/ for any imports of `_parse_timeout` from
      `a2kit.tool`. Update to `a2kit._timeout` if found.
- [x] 2.5 Remove `# noqa: A2K014` from `tool.py:1`.
- [x] 2.6 Verify SLOC drops below 500:
      `wc -l src/a2kit/tool.py`.

## 3. Mirror test files

- [x] 3.1 If `tests/packages/di/test_teardown.py` doesn't exist,
      either create a stub-with-a-test (so the mirror rule is
      satisfied) or add `src/a2kit/packages/di/teardown.py` to
      `ALLOW_LIST` in `src/a2kit/packages/lint/rules/mirror.py`
      with rationale (existing teardown coverage is in
      `tests/test_singleton_teardown.py`).
- [x] 3.2 If `tests/test__timeout.py` doesn't exist (test mirror
      for `_timeout.py`), either create a stub-with-a-test or
      add `src/a2kit/_timeout.py` to `ALLOW_LIST` with rationale
      pointing at `tests/test_timeout_decorator.py`.

## 4. Verify

- [x] 4.1 `make test` green; 864 tests still pass (no shifted
      import paths broken).
- [x] 4.2 `make lint` green; A2K014 produces zero warnings on
      `container.py` and `tool.py`.
- [x] 4.3 Import graph check:
      `uv run python -c "from a2kit.packages.di.teardown import teardown_order; from a2kit._timeout import _parse_timeout; print('ok')"`
- [x] 4.4 Public-API smoke: import `a2kit`, call `read()` and
      `app.singleton(T, factory, teardown=...)` once — confirms
      both modules wire correctly through the public surface.

## 5. Out-of-scope

- [x] 5.1 Further `tool.py` decomposition (extracting list_view-only
      helpers `_check_list_return_annotation`,
      `_derive_selectable_fields`, etc.). Could shave more SLOC but
      the file remains coherent at ~500. Defer until A2K014 fires
      again.
- [x] 5.2 Further `container.py` decomposition (extracting
      `_ParamSpec`, `_factory_callable`, `_factory_params`). Same
      reasoning — only worth doing if file grows again.

## 6. No spec changes

This is module-layout refactoring; no capability spec is affected.
Public types and symbols stay where consumers expect them. No
`specs/` directory needed under this change.
