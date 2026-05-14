# Tasks — remove App(health_tool=) flag

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` + `make lint` green.
- [x] 0.2 Inventory consumer references to `health_tool=` in
      `docs/`, `examples/`, `templates/` if any. Grep:
      `grep -rn "health_tool" docs/ examples/`.

## 1. Remove the parameter from App

- [x] 1.1 In `src/a2kit/app.py::App.__init__`, drop the
      `health_tool: bool = False` parameter from the signature.
- [x] 1.2 Add a guard at the top of `__init__` that catches
      `health_tool` smuggled through `**kwargs` (if `App` accepts
      kwargs) or rely on Python's natural `TypeError` for the
      unknown kwarg. If natural `TypeError` doesn't carry a hint,
      explicit `**_kw: Any` + guard is cleaner:
      ```python
      def __init__(self, name: str, *, lifespan=None, debug=False, **_kw):
          if "health_tool" in _kw:
              raise TypeError(
                  "App(health_tool=...) was removed in v0.34. "
                  "Register a check with @app.health_check to "
                  "auto-install the _meta.health tool, or omit the "
                  "flag if you don't need health checks."
              )
          if _kw:
              raise TypeError(f"Unexpected kwargs: {sorted(_kw)}")
          ...
      ```
- [x] 1.3 Remove the conditional install in the body:
      `if health_tool: self._install_health_tool()` deletes
      cleanly; `_install_health_tool` becomes called only from
      `health_check(...)`.
- [x] 1.4 Remove `HealthRegistry(enabled=health_tool)` indirection
      in `__init__`. The registry's `enabled` state is now driven
      exclusively by the first `@app.health_check` call.

## 2. HealthRegistry audit

- [x] 2.1 Audit `HealthRegistry.__init__` — if `enabled=` is only
      reachable from the now-removed code path, drop the
      parameter. If it has external callers (probably not), leave
      it but trace and document.
- [x] 2.2 Confirm `_install_health_tool` idempotency continues to
      hold when called only from `health_check`.

## 3. Test surface

- [x] 3.1 Add `tests/test_app.py::test_health_tool_kwarg_raises`:
      - GIVEN `app = a2kit.App("a", health_tool=True)`
      - WHEN the constructor evaluates
      - THEN `TypeError` is raised
      - AND the message contains `"health_check"`
- [x] 3.2 Remove any existing test that asserts
      `App(health_tool=True)` is a valid construct (the no-op-when-
      checks-registered scenario from v0.33). Grep:
      `grep -rn "health_tool=True" tests/`.
- [x] 3.3 Confirm `tests/test_health_probe.py` (or wherever the
      health-probe tests live) still passes — auto-install via
      `@app.health_check` is the only path now.

## 4. Spec delta

- [x] 4.1 Author `openspec/changes/remove-health-tool-flag/
      specs/health-probe/spec.md`:
      - REMOVED Requirement: "Built-in health tool" — the
        `App(health_tool=True)` install path
      - ADDED Requirement: "Health tool installs exclusively via
        `@app.health_check`"
      - Scenario: `App` constructed with the flag raises
        `TypeError`
      - Scenario: `@app.health_check` on a fresh app installs
        `_meta.health` idempotently

## 5. CHANGELOG

- [x] 5.1 In `CHANGELOG.md` `Unreleased` section, add a
      BREAKING entry:
      ```
      ### Breaking — `App(health_tool=)` removed
      ```
      with the migration recipe (drop the flag; register a check).
- [x] 5.2 Update the migration table to include this row.

## 6. Verify

- [x] 6.1 `make test` green; the new test passes and no test
      still constructs `App(health_tool=True)`.
- [x] 6.2 `make lint` green.
- [x] 6.3 Repro: import a consumer-style app with `health_tool=True`
      — observe the raise, message contains the migration hint.

## 7. Out-of-scope

- [x] 7.1 Removing `@app.health_check` itself. The decorator is
      the only install path now; not deprecating it.
- [x] 7.2 Changing the `_meta.health` tool's wire shape or hidden-
      by-default behaviour. Unchanged.
