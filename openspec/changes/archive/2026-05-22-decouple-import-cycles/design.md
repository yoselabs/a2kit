## Context

`packages/` and `app.py` carry three import cycles: `cli ↔ mcp`,
`mcp ↔ codemode`, and `app ↔ health`. The first two are runtime cycles
papered over by function-local imports. The third is a `TYPE_CHECKING`
cycle — `ty` survives it, but it is a real design cycle.

The visible symptom is `_wrappers.py`: 21 `: Any` annotations where
`App` / `Router` belong, because importing those types would complete
the `cli ↔ mcp` cycle.

An earlier draft of this proposal mis-diagnosed the `codemode` edge as
living in `build_code_mode_transform`. It does not — that function
never touches the server. The edge is in `run_code`, a CLI-side helper
that happens to live in the `codemode` package.

## Goals / Non-Goals

**Goals**

- The package import graph — `packages/*` *and* core (`a2kit.*`) — is a
  DAG.
- `_wrap_with_*` functions are typed against `App` and `Router`.
- Each cycle is broken structurally (relocation / inversion), not by
  deferring an import.

**Non-Goals**

- Not adding the layering lint — that is `enforce-package-layering`.
- Not migrating the CLI dispatch path or unifying it with MCP.
- Not removing the `cli → mcp` deferred import in `_serve.py` (a
  cold-start guard, not a cycle workaround — a legal forward edge once
  the back-edges are gone).

## Decisions

### D1. Context primitives are a low-level package

`StderrToolContext` is a `ToolContext` implementation — transport
neutral. It lived in `packages/cli/context.py` only by accident of who
wrote it first. A `packages/context` package holds it below both
transports. It is not a pure leaf: `_emit` lazily imports
`a2kit.packages.ldd` for the `format_ldd_line` wire-format primitive —
so in `enforce-package-layering`'s layer manifest `context` sits just
*above* `ldd`, not at the bottom. That lazy import is the only
`a2kit.packages.*` edge out of `context`; it reaches no transport
package, which is what kills the cycles. `StderrToolContext` mirrors
`fastmcp.Context` (elicitation result types) and so joins the
`A2K-IMPORT-DISCIPLINE` fastmcp allowlist — the `fastmcp` import stays
lazy, exactly as in today's `cli/context.py`.

### D2. Relocate `run_code`, do not inject a server

`run_code` builds an MCP server, wraps it in a `fastmcp.Client`, and
runs sandbox code. Its only caller is the CLI `code` subcommand; the
MCP `execute` tool builds itself independently in
`A2kitCodeMode._make_execute_tool`. `run_code` is therefore CLI
orchestration mis-filed in `codemode`. Moving it to a lazily-loaded
`cli` module breaks the cycle and puts the function with its caller.
This supersedes the earlier draft's "inject the server into
`build_code_mode_transform`" — that function was never in the cycle.

### D3. `run_checks` takes a `Resolver`, not an `App`

A health check is a callable with DI-resolvable parameters.
`run_checks` needs exactly the ability to resolve those parameters —
i.e. a `Resolver`. It does not need routers, descriptors, lifecycle, or
any other `App` surface. Narrowing the parameter to `Resolver` removes
`health`'s dependency on core and lets `health` sit cleanly in the
kernel layer. This also composes with `split-app-builder-runtime`: a
`Resolver`-typed `run_checks` is trivially callable from the sealed
runtime `App`.

### D4. Type `_wrappers.py` with the concrete `App` / `Router`

Once the `cli ↔ mcp` cycle is gone, `packages/mcp` can import
`a2kit.app` and `a2kit.routers` at module scope with no cycle (neither
core module imports `mcp`). A narrow `DispatchApp` protocol was
considered and rejected: there is one consumer, `App` is a stable core
type already imported elsewhere in `packages/mcp`, and a single-caller
protocol is premature abstraction — the same reasoning the earlier
draft applied to the rejected `ToolCatalog` protocol.
