# Tasks — app-time-tools-tuple-validation

## 0. Prerequisites

- [x] 0.1 Baseline: `make lint` + `make test` green.
- [x] 0.2 Search `src/`, `examples/`, `tests/` for any tool body
      where a method is decorated with `@a2kit.read/write/list_/tool`
      but NOT listed in its Router's `tools` tuple. Migrate or
      document as part of this task. The check below will raise
      on any such case.

## 1. Exception class

- [x] 1.1 Add `A2KitDecoratedMethodNotInTools(A2KitError, TypeError)`
      to `src/a2kit/exceptions.py`. Constructor:
      `(router_cls_name: str, missing: list[str])`. Message per
      D-EXCEPTION in design.md.
- [x] 1.2 Unit test in `tests/test_exceptions.py`: instantiate,
      check attributes, check rendered message contains the missing
      method names.

## 2. Validation helper

- [x] 2.1 Add `_validate_router_tools(router)` to
      `src/a2kit/app.py` (private module-level helper). Implementation
      per D-DETECTION-LOGIC: walks `cls.__dict__`, collects
      decorated methods, set-diffs against the tools tuple, raises
      on drift.
- [x] 2.2 `App.add_router` calls `_validate_router_tools(router)`
      after the existing router-type confirmation, before
      registering router-level providers/lifespan.

## 3. Tests

- [x] 3.1 In `tests/test_routers.py` (or new
      `tests/test_app_validation.py`): a Router with two
      decorated methods, only one in `tools`. Assert
      `app.add_router(R())` raises `A2KitDecoratedMethodNotInTools`
      with the missing method name in the message.
- [x] 3.2 Negative test: a Router with all decorated methods listed
      passes through `add_router` cleanly.
- [x] 3.3 Inheritance: a Router subclass inherits a decorated
      method from a base class but doesn't add it to its own
      `tools`. Assert this PASSES (we only check own-class
      attributes per D-DETECTION).
- [x] 3.4 `_MetaRouter` self-check: `App(health_tool=True)` builds
      successfully (regression — the synthetic router must obey
      the invariant).

## 4. Spec delta

- [x] 4.1 `openspec/changes/app-time-tools-tuple-validation/specs/router-conventions/spec.md`
      — add `## ADDED Requirements: App-time validation rejects
      decorated-but-unlisted methods`. Scenarios: (a) drift raises
      with the missing-method name; (b) all-listed passes; (c)
      inherited decorated methods don't fail.

## 5. Verify

- [x] 5.1 `make lint` green.
- [x] 5.2 `make test` green; new tests pass.
- [x] 5.3 Build a fresh app with `health_tool=True`; confirm no
      regression.
