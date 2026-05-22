## Why

After `decouple-import-cycles`, the import graph is acyclic — but
nothing stops it regressing. The existing `A2K-PKG-INIT-IMPORT` lint
rule catches only a submodule importing *its own* package `__init__`;
it is blind to cross-package cycles, to layer-order violations, and to
the core-to-package edges that produced the worst cycle
(`app.py ↔ packages/health`).

Three structural facts are currently unenforced:

- **No layer DAG.** `cli`, `mcp`, `codemode` sit above the kernel
  packages, which sit below core — but that is convention, not a gate.
- **Core is an unmodeled layer.** `app.py` imports kernel packages
  *and* is imported back by `health` / `connections`. A layer model
  that covers only `packages/*` cannot see the `app ↔ health` cycle at
  all — it spans the core boundary.
- **Package front doors are decorative.** `app.py` imports
  `packages.di.container`, `packages.di.scope`, `packages.di.resolver`,
  `packages.formatter.inference` — reaching past each package's
  `__init__`. ADR 0004 declares `packages.*.__init__` the front door;
  nothing enforces it is the *only* door.

This change turns all three into lint gates.

## What Changes

- A layer manifest assigns every importable unit — `packages/*` **and
  core (`a2kit.*` top-level modules, as one pseudo-unit)** — to an
  ordered layer. (Applied manifest — corrected from the original draft:
  `context` joins the kernel layer, since `context` lazily imports
  `ldd`; `context → ldd` is a same-layer non-cycle edge, which the rule
  permits. That collapses the original six layers to five.)
  - L0 — kernel: `di`, `formatter`, `ldd`, `health`, `select`, `lint`,
    `context`
  - L1 — `core` (the top-level `a2kit.*` modules)
  - L2 — `connections`, `dispatch`
  - L3 — `cli`, `mcp`, `codemode`, `otel`
  - L4 — `testing`
  - The foundational core modules `a2kit.exceptions` and
    `a2kit._context_protocol` (leaf type/exception definitions) are
    layer-exempt import *targets*; the public re-export facades
    (`__init__.py` files, `a2kit/testing.py`) are exempt importers.
- New lint rule **`A2K-LAYER`**: a unit may import only units in a
  strictly-lower layer (plus its own); a same-layer import MUST NOT
  close a cycle. The rule governs core↔package edges in both
  directions, and **inspects `TYPE_CHECKING`-guarded imports** — a
  type-only cycle is still a cycle (the `app ↔ health` cycle hid in
  exactly such an import).
- New lint rule **`A2K-PKG-FRONT-DOOR`**: importing
  `a2kit.packages.X.<submodule>` from outside package X is forbidden;
  cross-package imports target `a2kit.packages.X` (the `__init__`). A
  documented allowlist covers deliberate exceptions.
- The package front doors are opened: `di` / `cli` / `mcp` already
  re-export their public types; `formatter/__init__.py` gains
  `infer_format_hint` and `di/__init__.py` gains `lazy_inner_type`.
  All 15 deep imports — in `app.py`, `signature.py`, `tool.py`,
  `cli/_serve.py`, `cli/builder.py`, `connections/dispatch.py`,
  `health/__init__.py`, `testing/client.py`, `a2kit/__init__.py` —
  are rewritten onto the front doors.
- Both rules ship **directly as hard error**: because this change
  cleans every violation in the same pass, the warn-first window
  collapses to zero (the warn-first rollout matters only when the
  rule ships ahead of the cleanup).
- Refresh `module-layout-discipline`'s `__init__.py`-count scenario —
  the formula `2 + N + R` tracks `N` dynamically, so `context` (from
  `decouple-import-cycles`) and `dispatch` (from
  `extract-dispatch-pipeline`) are already covered.

## Capabilities

### Modified Capabilities

- `module-layout-discipline`: gains layer-manifest (core included),
  `A2K-LAYER`, and `A2K-PKG-FRONT-DOOR` requirements; the
  `__init__.py`-count scenario is corrected.

## Impact

- Two new static lint rules in `static.py::ALL_RULES`.
- `app.py` / `signature.py` / `tool.py` import lines rewritten;
  `di` / `formatter` `__init__.py` gain explicit re-exports.
- Any future cycle, layer violation, or past-the-front-door import
  fails `make lint` — including type-only cycles.
- **Depends on `decouple-import-cycles` and
  `extract-dispatch-pipeline`**: the graph must already be acyclic and
  front-door-clean (and the `dispatch` package must exist) before
  either rule can flip from warn to error.
