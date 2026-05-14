# Loud-error guard on renamed TestClient method

## Why

a2web v0.6.0 surfaced this as round-9 consumer feedback after
bumping to v0.33.0:

```python
async with make_client(app) as c:
    out = await c.call("demo.ping", msg="hi")
    # AttributeError: 'TestClient' object has no attribute 'call'
```

The canonical pattern across rounds 6–8 was `await client.call(...)`.
v0.33 renamed `.call` to `.invoke` without a migration table row.
The current `AttributeError` is technically loud, but the message
("no attribute 'call'") does not name the new method or suggest the
migration. Consumers find this by running things and watching them
break.

**Not adding an alias**: per project principle, dead surface should
crash, not gracefully degrade. The fix isn't to make `.call` work —
the fix is to make `.call` crash *with a migration hint*. This
mirrors v0.33's "loud failure with embedded migration hint" pattern
already applied to `@a2kit.read(idempotent=...)` etc.

## What Changes

- **MODIFY** `TestClient` in
  `src/a2kit/packages/testing/client.py`: add a `__getattr__` that
  intercepts the known-renamed name(s) and raises a `TypeError`
  with the explicit migration string:
  ```
  TestClient.call(...) was renamed to TestClient.invoke(...) in
  v0.33. Update the call site; no alias is provided.
  ```
- **DOCUMENT** the rename in CHANGELOG.md (retroactive 0.33 entry
  or under Unreleased). The omission of the rename from the v0.33
  migration table was the root cause; documenting now closes that
  gap.
- **ADD** a scenario in the `in-process-test-client` spec
  documenting the loud-error contract: calling the v0.32 spelling
  raises `TypeError` (not `AttributeError`) with the embedded hint.

## What Doesn't Change

- `.call` is not restored as an alias. Consumers migrate the call
  sites; the framework will not host backward-compat aliases for
  renamed surfaces.
- No `DeprecationWarning`. No "transitional period." The rename is
  effective immediately; the only difference vs. the current state
  is the quality of the error message.

## Impact

- One `__getattr__` on `TestClient` (~10 lines).
- One spec scenario.
- One CHANGELOG row.
- Consumer cost: same as today (still must migrate `.call` → `.invoke`).
- Consumer benefit: the error names the new method instead of just
  saying "no attribute 'call'".

## Pattern this establishes

This is a reusable pattern for future renames on canonical types:

```python
class TestClient:
    _MIGRATED_NAMES: ClassVar[dict[str, str]] = {
        "call": "invoke",
    }
    def __getattr__(self, name: str) -> Any:
        if name in self._MIGRATED_NAMES:
            new = self._MIGRATED_NAMES[name]
            raise TypeError(
                f"TestClient.{name}(...) was renamed to "
                f"TestClient.{new}(...). Update the call site; "
                f"no alias is provided."
            )
        raise AttributeError(f"'TestClient' object has no attribute {name!r}")
```

The dict makes adding future renames a one-line patch. The pattern
could be lifted into a helper if a third canonical type ever needs
the same treatment, but YAGNI for now.

## Sister change

The `canonical-api-drift-gate` proposal catches this class of bug
**before release**. This proposal handles the case where a rename
already shipped without notice. The two are complementary:

```
prevention (drift gate)  ←→  remediation (loud-error guard)
```
