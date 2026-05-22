## Why

a2kit has two consumers with asymmetric constraints. The **CLI** is
local, single-user, cold-start-critical, and MUST NOT import fastmcp
(`import a2kit` on the CLI path is ~318ms; with fastmcp ~3.6s —
`A2K-IMPORT-DISCIPLINE` confines fastmcp to `packages/mcp/`). The
**MCP server** already carries fastmcp.

Both consumers run the same per-tool dispatch concerns. Five of the six
are transport-neutral — enrichers, ldd-state + ctx synthesis, timeout,
dispatch-hook, router-lazy-enter — and today they are **implemented
twice**: once in `cli/runtime.py` + `cli/builder.py`, once in
`mcp/_wrappers.py`. The two implementations have already drifted (the
CLI uses `anyio.fail_after` for timeout; MCP uses its own
`_wrap_with_timeout`), and `router-lazy-enter` has no visible CLI path
at all — a silent parity gap. The MCP side additionally hand-stacks its
six `_wrap_with_*` closures in a fixed order encoded only in a comment.

FastMCP ships its own middleware system — but it cannot own these
concerns. FastMCP middleware is server-only, and the CLI consumer
cannot import fastmcp. A transport-neutral dispatch pipeline is
therefore *required by the consumer model*; it is not a reinvention of
FastMCP middleware.

## What Changes

- New **fastmcp-free** package `a2kit.packages.dispatch` holding the
  five transport-neutral dispatch stages as a typed, ordered, foldable
  pipeline. It is deliberately absent from the `A2K-IMPORT-DISCIPLINE`
  fastmcp allowlist — the lint rule keeps it fastmcp-free.
- A `DispatchStage` protocol — named *stage*, not *middleware*: a2kit
  already forwards real FastMCP middleware via `add_mcp_middleware`,
  and reusing the word collides. Each stage: `wrap(fn, spec) -> fn`,
  `spec: ToolBuildSpec`.
- The canonical stage order is one module-level ordered tuple in
  `packages/dispatch`, with the ordering rationale on it.
- Both adapters fold the **same** pipeline:
  - the MCP adapter folds it and appends its one MCP-wire-specific
    stage, the error-envelope (`ToolError(json)`);
  - the CLI adapter folds it and appends its own error → exit-code
    mapping.
- The error-envelope splits into a transport-neutral "capture
  exception → structured error" stage (in `packages/dispatch`) plus
  per-transport rendering, mirroring ADR 0014's `(value, consumer)`
  rendering seam.
- The duplicated CLI dispatch code (`cli/runtime.py`'s inline
  timeout/ldd/ctx, `cli/builder.py::_wrap_with_enricher`) and the MCP
  `_wrap_with_*` chain are both deleted in favor of the shared pipeline.

**BREAKING**: none on the consumer-facing surface — `_wrap_with_*` and
the CLI inline wrappers are framework-internal.

## Capabilities

### New Capabilities

- `dispatch-pipeline`: a fastmcp-free, transport-neutral dispatch
  pipeline — a folded sequence of typed `DispatchStage`s — shared by
  the CLI and MCP adapters; each adapter adds only its own error
  rendering.

## Impact

- One implementation of the five neutral concerns instead of two; the
  CLI/MCP drift and the `router-lazy-enter` parity gap are closed.
- The CLI cold path stays fastmcp-free — `packages/dispatch` imports no
  fastmcp.
- MCP `_build_one_tool` and the CLI `runtime.py` dispatch both shrink
  to "fold the pipeline, append the transport's error stage".
- **Depends on `decouple-import-cycles`**: the pipeline is typed
  against `App` / `Router` (importable only once the `cli ↔ mcp` cycle
  is gone), and the `_wrap_with_*` content moves out of `_wrappers.py`
  into the new package.
- `enforce-package-layering` gains `dispatch` in the layer manifest.
