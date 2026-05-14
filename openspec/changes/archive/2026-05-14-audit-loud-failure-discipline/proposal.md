# Audit-driven loud-failure / no-defensive-typing cleanup

## Why

After codifying the "loud crash with migration hint, no backward
compat, no silent errors" principles in `CLAUDE.md`, a sweep of
`src/a2kit/` surfaced five concrete violations of those rules. They
predate the new rules — none were introduced in this session — but
each is small, well-bounded, and worth closing now while the
principles are fresh and a v0.34 release is being staged.

Findings (grouped by pattern):

### Pattern A — silent fallback returning None / dead-default sentinel

| site                                                     | smell                                                              |
|----------------------------------------------------------|---------------------------------------------------------------------|
| `src/a2kit/tool.py:242 _compute_report_schema`           | `except Exception: return None` — no log, callers can't distinguish "no schema available" from "schema computation crashed" |
| `src/a2kit/packages/health/__init__.py:114 _version`     | `return getattr(app, "version", None) or "unknown"` — silently substitutes "unknown" if version missing; obscures misconfig |
| `src/a2kit/packages/lint/runtime.py:43`                  | `getattr(t, "name", "")` — empty-string fallback on what should be a guaranteed attribute |

The shape: a function returns a "safe" default when introspection
fails. The default is indistinguishable from a legitimate empty
value. Consumers can't tell why a feature didn't activate.

### Pattern B — defensive `hasattr` against framework-known types

| site                                                       | smell                                              |
|------------------------------------------------------------|---------------------------------------------------|
| `src/a2kit/packages/mcp/server.py:402-405`                 | `app.ldd.sinks if hasattr(app, "ldd") else ()` ×3 |
| `src/a2kit/packages/cli/runtime.py:115`                    | `if app is not None and hasattr(app, "ldd")`      |

The shape: code receives `app: a2kit.App` (type-known) but checks
for the existence of attributes the `App` class always declares.
Dead defense from a pre-typed era; today these branches confuse
readers and obscure intent.

### Pattern C — `_kw`-style silent absorption

The `App.__init__` does not currently use `**_kw`-with-guard;
unknown kwargs raise the natural `TypeError`. **No bug here**, but
the proposal codifies the pattern in `App.__init__` and
`Router.__init__` to standardise the migration-hint shape across
future changes. This is preventive — adding `**_kw` plus the guard
costs ~5 lines per constructor and lets future kwarg-removals
carry hints without re-modifying the constructor.

(The `cross-transport-parity-strict` proposal handles the related
"runtime dispatcher silently drops unknown call-time kwargs" case
— that's the call site of `fn(**call_kwargs)` rather than the
constructor.)

## What Changes

### Pattern A — replace silent fallbacks with WARN-then-raise or WARN-then-return

- **MODIFY** `src/a2kit/tool.py::_compute_report_schema`:
  - Add `_log.warning(...)` with the `report_type.__name__` and the
    exception class+message when `TypeAdapter` raises.
  - Keep the `return None` since decoration must not abort, but the
    log line makes the failure observable.
  - Mirror the `_WARN_ONCE` pattern from
    `src/a2kit/signature.py::resolve_hints` so noise stays bounded.

- **MODIFY** `src/a2kit/packages/health/__init__.py::_version`:
  - Replace the silent `"unknown"` fallback with explicit raising
    OR a single WARN log when `version` is absent. App identity
    without a version is a misconfig worth surfacing.

- **MODIFY** `src/a2kit/packages/lint/runtime.py:43`:
  - Drop the `""` fallback; let `AttributeError` raise naturally
    if a tool descriptor lacks `.name`. Add a precondition assert at
    the entry of the function so the failure attributes to the call
    site, not deep inside a list comprehension.

### Pattern B — drop defensive hasattr

- **MODIFY** `src/a2kit/packages/mcp/server.py:402-405`:
  ```python
  # before
  app_sinks: tuple[Any, ...] = app.ldd.sinks if hasattr(app, "ldd") else ()
  container = app.container() if hasattr(app, "container") else None
  dispatch_hook = app.dispatch_hook() if hasattr(app, "dispatch_hook") else None

  # after
  app_sinks: tuple[Any, ...] = app.ldd.sinks
  container = app.container()
  dispatch_hook = app.dispatch_hook()
  ```
  The type annotation `app: App` carries the invariant.

- **MODIFY** `src/a2kit/packages/cli/runtime.py:115`:
  ```python
  # before
  if app is not None and hasattr(app, "ldd"):
      sinks = app.ldd.sinks

  # after — if app is optional, narrow:
  if app is not None:
      sinks = app.ldd.sinks
  ```
  If `app is None` is a real case (it is — the runtime dispatcher
  is used outside App contexts in some test paths), document that
  and use a clean `if app is None` guard. The `hasattr` is the
  defensive part to drop.

### Pattern C — standardise constructor kwarg guard

- **MODIFY** `src/a2kit/app.py::App.__init__`:
  Add `**_kw: Any` after the documented parameters; raise `TypeError`
  on any leftover key with a "See CHANGELOG for v0.34 removals"
  message. This is the surface the `remove-health-tool-flag`
  proposal will leverage.

- **MODIFY** `src/a2kit/routers.py::Router.__init__`:
  Same pattern. (Lower priority — Router subclasses don't typically
  receive kwargs, but the pattern locks in the convention.)

## Spec impact

One requirement added to the `core-purity` capability spec
codifying the no-silent-fallback / no-defensive-hasattr rules so
future contributors (and future a2kit lint rules) can enforce them
mechanically.

A future `a2kit lint static` rule could check for these patterns
AST-side. Out of scope here; the requirement opens the door.

## Risk

Low across the board.

- **Pattern A**: behavior shifts from "silently hide" to "log + hide"
  or "raise". The two log additions are pure additive; the lint
  runtime drop-the-default could surface a bug that the empty-string
  was hiding (in which case the bug should be fixed at its source).
- **Pattern B**: the `hasattr` branches are dead; removing them
  changes nothing for in-range `app: App` callers. If a duck-typed
  caller exists (no current evidence), they get a loud
  `AttributeError` — which is the correct behaviour per the new
  rules.
- **Pattern C**: standardisation; same external behaviour, better
  error message shape.

## Why one proposal instead of five

Each finding is ~10 lines of change. Splitting would generate
proposal/tasks/spec-delta scaffolding overhead at ratio higher than
the actual fix. The proposal stays coherent because every finding
maps to one of the four `CLAUDE.md` core principles.

Larger sibling work that grows out of this audit (e.g. an
`a2kit lint static` AST rule that catches Pattern A automatically)
gets its own proposal once the cleanup lands.
