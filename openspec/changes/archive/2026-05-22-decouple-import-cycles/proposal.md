## Why

The package graph carries three import cycles. Two are
transport-to-transport; one crosses the core boundary. (A fourth,
`a2kit.testing ↔ packages/testing`, was suspected during exploration
but found already absent — see the last bullet.)

- **`cli ↔ mcp`** — `cli/_serve.py` imports
  `mcp.server.build_mcp_server`; `mcp/_wrappers.py` imports
  `cli.context.StderrToolContext`.
- **`mcp ↔ codemode`** — `mcp/server.py` imports
  `codemode.build_code_mode_transform`; `codemode.run_code` imports
  `mcp.server.build_mcp_server`.
- **`app.py ↔ packages/health`** — `app.py` constructs
  `HealthRegistry` and calls `run_checks(app)`; `packages/health`
  imports `App` (under `TYPE_CHECKING`, so `ty` survives it — but it is
  a genuine design cycle: neither file is comprehensible alone, and
  `app.py` defers both `health` imports into function bodies to live
  with it).
- **`a2kit.testing ↔ packages/testing`** *(suspected, not real)* — the
  core tier-2 shim `testing.py` imports `packages/testing` at module
  scope. Exploration flagged apparent back-imports in `fixtures.py` /
  `null_context.py`, but those lines are docstring *examples*
  (`from a2kit.testing import ambient_for_tests_autouse` shown inside a
  consumer-conftest snippet), not import statements. No back-edge
  exists; the shim is already a pure one-directional re-export.

102 function-local imports in `src/` paper over these. The cost:
`mcp/_wrappers.py` carries 21 `: Any` annotations because importing
`App` / `Router` would close the `cli ↔ mcp` cycle.

The leaf kernel (`di`, `formatter`, `ldd`, `select`) is genuinely
acyclic. The rot is localized — the transport packages, the
`app ↔ health` knot, and the testing shim — which makes it cheap to
fix now and a prerequisite for the `enforce-package-layering` lint.

## What Changes

- New low-level package `a2kit.packages.context` holds transport-neutral
  tool-context implementations (`StderrToolContext` and siblings). It
  imports no transport package; its only `a2kit.packages.*` dependency
  is a lazy import of `a2kit.packages.ldd` (the `format_ldd_line`
  wire-format primitive, inside `_emit`). `mcp` and `cli` import context
  primitives from it — the `mcp → cli` back-edge is removed.
- `run_code` moves from `packages/codemode` to `packages/cli`. It
  builds an MCP server, wraps it in a `fastmcp.Client`, and runs
  sandbox code — a CLI-side orchestration helper whose sole caller is
  the CLI `code` subcommand. With it gone, `codemode` imports nothing
  from `mcp` — the `codemode → mcp` back-edge is removed. (Its stale
  docstring — claiming the MCP `execute` tool also uses it — is
  corrected; `_make_execute_tool` builds that tool independently.)
- `run_checks` is retyped to take a `Resolver`, not `App`. Health
  checks need only DI resolution to run their callables; they do not
  need the composition root. `packages/health` drops its
  `TYPE_CHECKING` import of `App` — the `health → app` back-edge is
  removed.
- `packages/testing` is verified to import nothing from the core
  `a2kit.testing` shim — no code change is needed (the suspected
  back-edge was a misread of docstring examples). A regression test
  locks the shim as a pure one-directional re-export.
- With all four cycles gone, `mcp/_wrappers.py` imports `App` and
  `Router` at module scope; the `: Any` annotations on `_wrap_with_*`
  become real types.
- Resulting graph is a DAG: `cli → {mcp, codemode}`, `mcp → codemode`,
  `codemode → formatter`, `app → health`, everything → `context`.

**BREAKING**: `run_code` moves to `a2kit.packages.cli`; the old
`a2kit.packages.codemode.run_code` path raises with a migration hint.
`run_checks` signature changes from `(app)` to `(resolver)`.
`StderrToolContext` moves from `a2kit.packages.cli.context` to
`a2kit.packages.context`.

## Capabilities

### New Capabilities

- `import-acyclicity`: the package import graph (core included) is a
  DAG; context primitives are a transport-neutral leaf package;
  `run_code` is CLI-owned; health checks resolve via `Resolver`, not
  `App`; MCP dispatch wrappers are typed.

### Modified Capabilities

None. Adding the `context` package leaves `module-layout-discipline`'s
`__init__.py`-count scenario stale — but it is *already* stale (it
asserts N=9 plugin packages; the repo has 12). `enforce-package-layering`
owns that refresh.

## Impact

- Three import cycles removed; the graph becomes a DAG that the
  `enforce-package-layering` lint can lock.
- ~21 `: Any` annotations in `_wrappers.py` resolved to real types.
- Cold-start unaffected — `context` is a tiny leaf; `run_code` lands in
  a lazily-loaded CLI module so the `fastmcp` / `build_mcp_server`
  import stays off the cold path (same discipline as `_serve.py`).
- Migration surface: `run_code` importers (CLI internal only),
  `run_checks` callers, `StderrToolContext` importers.
- Prerequisite for `extract-dispatch-pipeline` (needs typed
  `App` / `Router`) and `enforce-package-layering` (needs a clean
  graph before the layering lint can flip to error).
