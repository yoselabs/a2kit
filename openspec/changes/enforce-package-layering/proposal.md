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
  ordered layer:
  - L0 — `context`
  - L1 — `di`, `formatter`, `ldd`, `health`, `select`, `lint`
  - L2 — `core` (the top-level `a2kit.*` modules)
  - L3 — `connections`, `dispatch`
  - L4 — `cli`, `mcp`, `codemode`, `otel`
  - L5 — `testing`
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
- `packages/di/__init__.py`, `packages/formatter/__init__.py`, and
  `packages/mcp/__init__.py` re-export their public types
  (`Container`, `Scope`, `Resolver`, `infer_format_hint`,
  `build_encoding_plan`, `build_mcp_server`) so callers reach them via
  the front door. `build_mcp_server` is deep-imported today by
  `cli/_serve.py`, `packages/testing`, and `codemode` — all must move
  onto the front door or the rule cannot flip to error.
- `app.py`, `signature.py`, `tool.py` rewrite deep imports to
  front-door imports.
- Both rules ship **warn-only**, then flip to hard error once
  violations are zero — the proven `A2K-CORE-CLEAN` rollout pattern.
- Refresh `module-layout-discipline`'s stale `__init__.py`-count
  scenario (it asserts N=9 plugin packages; the repo has 12, and
  `decouple-import-cycles` adds `context` for 13).

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
