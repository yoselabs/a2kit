# Split oversized core files (container.py + tool.py)

## Why

Two core files exceed the A2K014 SLOC budget (500 lines) and currently
carry `# noqa: A2K014` suppressions:

| file                                          | SLOC | budget | overage |
|-----------------------------------------------|------|--------|---------|
| `src/a2kit/packages/di/container.py`          | 567  | 500    | +67     |
| `src/a2kit/tool.py`                           | 537  | 500    | +37     |

Both files grew during the v0.32-recovery wave: `container.py` gained
the topological teardown machinery (`_build_teardown_edges`,
`teardown_order`, `_teardowns` registration), and `tool.py` gained
timeout parsing (`_parse_timeout`) plus the `timeout=` parameter
threaded through all three verb decorators.

The A2K014 budget exists to keep individual files comprehensible at
a glance. Each of these files now mixes two coherent concerns that
can be split without losing locality:

```
container.py = [ DI core resolution ]  +  [ teardown topology ]
tool.py      = [ verb decorators ]    +  [ timeout parsing helpers ]
```

The split is **mechanical and low-risk** — both files have clear
internal seams, the new modules consume nothing the old file didn't
already, and the public surfaces (`Container`, `read`/`write`/`list_`)
stay where they are.

## What Changes

### container.py → container.py + teardown.py

- **NEW** `src/a2kit/packages/di/teardown.py` housing:
  - `_build_teardown_edges` helper
  - `teardown_order` algorithm (Kahn's with cycle break + WARN)
  - any teardown-specific exception types if separable
- **MODIFY** `Container.register_singleton(..., teardown=...)`
  and `Container.teardown_order()` to delegate into the new module.
  The methods stay on `Container` (public surface unchanged) but
  bodies become one-line wrappers.

### tool.py → tool.py + _timeout.py

- **NEW** `src/a2kit/_timeout.py` housing:
  - `_parse_timeout(value: float | int | str | None) -> float | None`
  - `_TIMEOUT_SUFFIX_MULTIPLIERS` constant
- **MODIFY** `tool.py` to `from a2kit._timeout import _parse_timeout`
  at the top of the relevant `_stamp` call site.

### A2K014 noqa removal

- **MODIFY** `src/a2kit/packages/di/container.py:1` — remove
  `# noqa: A2K014` (post-split SLOC should be under 500).
- **MODIFY** `src/a2kit/tool.py:1` — remove `# noqa: A2K014` (same).

## Impact

- **No public surface changes.** `Container.register_singleton` and
  `Container.teardown_order` keep their signatures and module path.
  `read`/`write`/`list_` stay in `a2kit.tool`. The `_timeout` and
  `teardown` modules are private (underscore-prefixed module name
  for `_timeout`, package-level for `teardown` since it's in a
  package).

- **Test stability.** No tests should require changes; if any test
  imported a private helper from `container.py` or `tool.py` by
  module path, those imports break — likely 0 hits.

- **Lint surface.** Two `# noqa: A2K014` suppressions disappear.
  A2K014 remains active and now enforces clean state without
  exemptions.

- **Cold-start budget.** New modules add ~zero import overhead —
  they're imported only when the host file is imported, and they
  consume nothing new.

## Risk

Very low. Mechanical extraction of well-bounded internal logic.
The main risk is import-cycle introduction if the new modules
accidentally import from their parent — both new modules should be
strict leaves (`teardown.py` imports nothing from `container.py`;
`_timeout.py` imports nothing from `tool.py`). Reviewers should
verify the import graph stays acyclic.
