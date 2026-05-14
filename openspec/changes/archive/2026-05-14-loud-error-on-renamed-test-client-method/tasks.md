# Tasks — loud-error guard on renamed TestClient method

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` + `make lint` green.

## 1. Implementation

- [x] 1.1 Add a `_MIGRATED_NAMES: ClassVar[dict[str, str]]` to
      `TestClient` in `src/a2kit/packages/testing/client.py`:
      ```python
      _MIGRATED_NAMES = {"call": "invoke"}
      ```
- [x] 1.2 Add `__getattr__` that intercepts known-renamed names and
      raises `TypeError` with the embedded migration string. Fall
      through to `AttributeError` for genuinely-unknown names.
- [x] 1.3 Mind interaction with `dataclass` / `attrs` / pydantic if
      `TestClient` uses any (it doesn't, but verify).

## 2. Test

- [x] 2.1 Add `test_call_raises_with_migration_hint` in
      `tests/test_in_process_client.py`:
      - GIVEN a `TestClient` instance
      - WHEN `await c.call(...)` is invoked
      - THEN `TypeError` is raised
      - AND the message contains `"renamed"` and `"invoke"`
- [x] 2.2 Add `test_genuinely_unknown_attribute_raises_attribute_error`:
      - GIVEN a `TestClient` instance
      - WHEN `c.completely_unknown_method` is accessed
      - THEN `AttributeError` is raised (not `TypeError`)
- [x] 2.3 Ensure `await c.invoke(...)` still works — regression
      guard on the canonical name.

## 3. Spec delta

- [x] 3.1 Author `openspec/changes/loud-error-on-renamed-test-client-method/
      specs/in-process-test-client/spec.md`:
      - ADDED Requirement: "TestClient surfaces renamed method names
        with embedded migration hints"
      - Scenarios for the migration-hint shape and the
        unknown-attribute pass-through

## 4. CHANGELOG

- [x] 4.1 Add migration table row to CHANGELOG.md (Unreleased
      section):
      | before | after |
      |---|---|
      | `await client.call(tool, **kwargs)` | `await client.invoke(tool, **kwargs)` (raises TypeError on `.call` with embedded hint) |
- [x] 4.2 Note the lack of alias in the entry — explicit signal that
      this is the project's stable rename pattern.

## 5. Verify

- [x] 5.1 Repro the consumer's exact shape:
      ```python
      async with make_client(app) as c:
          await c.call("demo.ping", msg="hi")
      ```
      Confirm the raise carries `"renamed"` and `"invoke"` in the
      message.
- [x] 5.2 `make test` green.
- [x] 5.3 `make lint` green.

## 6. Out-of-scope

- [x] 6.1 Restoring `.call` as an alias. Project principle: dead
      surface crashes, not gracefully degrades. Aliases hide
      migrations from consumers' read paths.
- [x] 6.2 Generalizing the pattern to other canonical types. Done
      lazily — if a second canonical type renames a method, lift
      the helper at that point. YAGNI for now.
- [x] 6.3 Catching the rename pre-release. That's the sister
      `canonical-api-drift-gate` proposal's job.
