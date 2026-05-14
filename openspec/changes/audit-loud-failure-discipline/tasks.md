# Tasks — audit-driven loud-failure / no-defensive-typing cleanup

## 0. Prerequisites

- [ ] 0.1 Baseline: `make test` + `make lint` green.
- [ ] 0.2 Re-run the audit greps from `CLAUDE.md` to confirm the
      finding set hasn't shifted since the proposal was written:
      ```bash
      grep -rn "except Exception\|except:" src/ --include='*.py' | grep -v "raise\|log\.\|_LOGGER\.\|# why:"
      grep -rn "hasattr(app," src/ --include='*.py'
      grep -rn "getattr(.*, *None) or" src/ --include='*.py'
      ```

## 1. Pattern A — silent fallbacks → WARN-then-degrade

- [ ] 1.1 `src/a2kit/tool.py::_compute_report_schema` — add WARN log
      before `return None` in the `TypeAdapter` failure path.
      Use the `_WARN_ONCE_*` pattern (one set per failure site) to
      bound noise. Include the report_type qualname and exception
      class+message.
- [ ] 1.2 `src/a2kit/packages/health/__init__.py::_version` — replace
      `return getattr(app, "version", None) or "unknown"` with a
      direct attribute access; on `AttributeError`, raise a
      `TypeError` with hint "App must declare a `version: str`
      attribute (used by the health probe; set in `App.__init__`)".
      Note: if `app.version` is genuinely optional, narrow the
      type signature instead of fall-through-with-default.
- [ ] 1.3 `src/a2kit/packages/lint/runtime.py:43` — drop the empty-
      string default in `getattr(t, "name", "")`. Add a precondition
      check at function entry that asserts each `t` has a `.name`,
      with a clear AssertionError or TypeError citing the caller.

## 2. Pattern B — drop defensive hasattr

- [ ] 2.1 `src/a2kit/packages/mcp/server.py:402-405` — remove the
      three `hasattr(app, "ldd"/"container"/"dispatch_hook")`
      branches. Direct attribute access; let `AttributeError`
      surface if some future caller passes a non-App.
- [ ] 2.2 `src/a2kit/packages/cli/runtime.py:115` — replace
      `if app is not None and hasattr(app, "ldd")` with
      `if app is not None`. Keep the None guard; drop the hasattr.

## 3. Pattern C — constructor kwarg guard

- [ ] 3.1 `src/a2kit/app.py::App.__init__` — add `**_kw: Any` after
      the documented parameters. Raise `TypeError` on any leftover
      key with the message shape from `CLAUDE.md` (name the kwarg,
      reference the CHANGELOG).
- [ ] 3.2 `src/a2kit/routers.py::Router.__init__` — same pattern.
      (Routers don't currently take subclass-supplied kwargs, but
      the guard locks in the convention.)

## 4. Tests

- [ ] 4.1 Add `tests/test_no_silent_fallbacks.py` covering:
      - `_compute_report_schema` failure path emits a WARN log
        (via `caplog`) and returns None
      - `_version` raises `TypeError` when `app.version` is absent
      - Lint runtime entry raises when `.name` is missing on a
        descriptor
- [ ] 4.2 Add `tests/test_app_init_kwarg_guard.py`:
      - `a2kit.App("a", unknown_kwarg=True)` raises `TypeError`
      - The error message mentions `unknown_kwarg` and the
        CHANGELOG
- [ ] 4.3 Confirm no existing test relied on the silent-fallback
      behaviour (grep for `_compute_report_schema` callers in
      tests).

## 5. Spec delta

- [ ] 5.1 Author `openspec/changes/audit-loud-failure-discipline/
      specs/core-purity/spec.md`:
      - ADDED Requirement: "No silent fallbacks for introspection
        failures"
      - ADDED Requirement: "Constructors validate against the
        declared parameter set"
      - ADDED Requirement: "No defensive hasattr against
        framework-typed objects"
      - Scenarios for each that point at the test names in task 4

## 6. CHANGELOG

- [ ] 6.1 Add migration table entries to CHANGELOG.md Unreleased
      section. Most are internal-only and don't need consumer-
      facing migration, but `App.__init__` going strict on kwargs
      is a breaking-shape change worth a row.

## 7. Verify

- [ ] 7.1 `make test` green; new tests pass.
- [ ] 7.2 `make lint` green.
- [ ] 7.3 Re-run audit greps from CLAUDE.md — the patterns flagged
      in the proposal should return zero hits in src/ (except those
      explicitly documented as legitimate, e.g. `ldd/__init__.py`
      sink fan-out).

## 8. Out-of-scope

- [ ] 8.1 An `a2kit lint static` AST rule for Pattern A / B. Worth
      a follow-up proposal once the manual cleanup lands and the
      patterns are well-shaped enough to AST-detect.
- [ ] 8.2 The runtime-dispatcher `fn(**call_kwargs)` silent-drop
      (call-site of unknown kwargs). Covered by sister proposal
      `cross-transport-parity-strict`.
- [ ] 8.3 The `getattr` calls that have legitimate
      protocol-detection use (e.g. `model_dump`, `__metadata__`,
      `__wrapped__`). These are duck-typing across third-party
      types, not framework-internal defenses. Left alone.
