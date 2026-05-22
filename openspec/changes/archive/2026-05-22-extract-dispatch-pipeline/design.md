## Context

a2kit has two consumers with asymmetric constraints. The CLI is local,
cold-start-critical, and MUST NOT import fastmcp. The MCP server
carries fastmcp by definition. Both run the same per-tool dispatch
concerns — and five of the six are transport-neutral yet implemented
twice (`cli/runtime.py` + `cli/builder.py` vs `mcp/_wrappers.py`). The
two implementations have already drifted, and `router-lazy-enter` is
missing from the CLI path entirely.

FastMCP ships a middleware system, but it is server-only — it cannot
serve the CLI consumer. So the shared concerns cannot live behind
fastmcp; they need a transport-neutral home.

## Goals / Non-Goals

**Goals**

- One implementation of the five transport-neutral dispatch concerns.
- That implementation is fastmcp-free, so the CLI cold path stays clean.
- Both the CLI and MCP adapters fold the same pipeline.
- The `router-lazy-enter` CLI parity gap is closed.

**Non-Goals**

- Not changing dispatch *behavior* — this is a structural refactor; the
  built chain must be observably equivalent (modulo the parity-gap fix).
- Not exposing dispatch stages as a public consumer surface.
- Not touching `add_mcp_middleware` — a2kit still forwards real FastMCP
  middleware unchanged.

## Decisions

### D1. A fastmcp-free package, enforced by omission from the allowlist

`packages/dispatch` is not on the `A2K-IMPORT-DISCIPLINE` fastmcp
allowlist. Any fastmcp import into it fails lint. This is the
load-bearing constraint: the CLI consumer cannot import fastmcp, so the
shared pipeline must not either.

### D2. Named "stage", not "middleware"

a2kit already forwards real FastMCP middleware via `add_mcp_middleware`.
Calling the pipeline units "middleware" would collide with that and
invite the "why two middleware systems?" question. They are dispatch
*stages*; the package is `dispatch`.

### D3. Five neutral stages in the pipeline; error rendering is per-transport

The error *shape* is transport-specific — `ToolError(json)` for MCP, an
exit code for the CLI — but error *capture* is not. So a
transport-neutral "capture exception → structured error" stage lives in
the pipeline, and each adapter renders the structured error its own
way. This mirrors ADR 0014's `(value, consumer)` rendering seam: one
captured value, consumer-specific rendering.

### D4. One timeout mechanism

The CLI uses `anyio.fail_after`; the MCP side uses its own
`_wrap_with_timeout`. The shared `TimeoutStage` picks one —
`anyio.fail_after`, transport-neutral and already a dependency — so the
two transports can no longer drift.

### D5. One `spec` parameter, conditional stages self-skip

`wrap(fn, spec: ToolBuildSpec)` replaces the varied `_wrap_with_*`
argument lists. Conditional stages (`TimeoutStage`, `DispatchHookStage`,
`RouterLazyEnterStage`) return `fn` unchanged when their concern does
not apply, so `DISPATCH_PIPELINE` stays a static tuple with one
canonical order.

### D6. Why not FastMCP middleware — the recorded answer

FastMCP middleware is server-only. The CLI consumer needs every one of
these five concerns and cannot import fastmcp. A transport-neutral
pipeline is therefore *required by the consumer model*, not a
reinvention of a FastMCP primitive. This is the answer to the
thin-core reviewer question "isn't this a second middleware system?" —
the pipeline owns exactly the concerns FastMCP middleware structurally
cannot reach.
