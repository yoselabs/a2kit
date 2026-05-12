## Why

`a2kit serve` crashes on first invocation against the FastMCP version
we already pin (`fastmcp>=3.2,<4`). `src/a2kit/packages/mcp/server.py:320`
calls `tool.disable()` per `_meta.*` tool; FastMCP 3.0 removed
`Component.disable()` and the runtime raises `NotImplementedError`
with the migration verbatim:

```
NotImplementedError: Component.disable() was removed in FastMCP 3.0.
Use server.disable(keys=['tool:_meta.health@']) instead.
```

Reproduced locally on `fastmcp 3.2.4`. **Every** consumer of
`a2kit==0.28.0` hits this on first `serve` — the floor pin masked
the breakage because no smoke test exercises `build_mcp_server`
with a `_meta` tool. a2web v0.6.0 (round-6 reporter) is currently
blocked on shipping a2kit-backed MCP servers, and the only
workaround is a downstream `fastmcp<3.0` pin that breaks our own
floor.

Two adjacent gaps surfaced while debugging:

1. `FunctionTool` imported from `fastmcp.tools.tool` raises
   `FastMCPDeprecationWarning` in 3.2.x — the canonical path is
   `fastmcp.tools.function_tool`. Same call site.
2. The `_meta.*` namespace contract is undocumented in
   `OPERATIONAL_CONTRACTS.md`. App authors can't tell whether
   `_meta` is closed (a2kit-only), what "hidden" means on the MCP
   wire vs. CLI, or whether their own `_meta.foo` tool is allowed.
   This bit the reporter mid-debug.

Fix the call site against the FastMCP 3 API, eliminate the
deprecation, and write down the namespace contract that the code
has been quietly enforcing.

## What Changes

- Replace per-tool `tool.disable()` with a single post-loop
  `server.disable(tags={"_meta"})` call in `build_mcp_server`.
  `_meta.*` tools stay registered (CLI surfaces them under
  `<app> _meta …`) but are hidden from `list_tools` AND not
  callable via the MCP `call_tool` wire — the FastMCP-3
  visibility transform blocks both. The `tags={"_meta"}` selector
  is robust to future `_meta.*` additions.
- Migrate the `FunctionTool` import from `fastmcp.tools.tool` to
  `fastmcp.tools.function_tool` to clear the deprecation warning.
- Add a smoke test: build an `App` with one router and assert
  `build_mcp_server(app)` succeeds, the `_meta.health` tool is
  registered, and it's filtered from the default `list_tools`
  output but still invocable by exact name. Fail mode is the
  exact `NotImplementedError` this change repairs.
- Document the `_meta.*` namespace contract in
  `OPERATIONAL_CONTRACTS.md` (≤200 words): namespace is closed
  to a2kit-internals; CLI surfaces `_meta` tools under
  `<app> _meta …`; MCP transport hides them from `list_tools`
  but they remain callable by exact name; user-defined
  `_meta.*` tool names are rejected at registration time with
  a clear error.
- Enforce the closed-namespace contract at registration: if a
  user tool's resolved name starts with `_RESERVED_TOOL_NAME_PREFIX`
  and it wasn't registered through a2kit's internal builders,
  raise a typed error at `app.run`/`build_mcp_server` time.

## Capabilities

### New Capabilities

None — this change uses existing capabilities only.

### Modified Capabilities

- `operational-contracts`: ADD a requirement documenting the
  `_meta.*` namespace contract end-to-end (closed namespace;
  CLI-visible / MCP-hidden split; cross-reference to the
  existing rejection rule in `health-probe`).

Mechanism details (the `server.disable(tags={"_meta"})` call,
the `FunctionTool` import path, the registration-time
rejection enforcement) are implementation of the existing
`health-probe` requirements ("Hidden from tool listings by
default" and "`_meta.*` namespace reserved"). No spec
modifications to `health-probe` are needed — the requirements
already describe the observable behaviour; this change brings
the implementation back into compliance with FastMCP 3.

## Impact

- **Code**: `src/a2kit/packages/mcp/server.py` (call-site rewrite,
  import migration, registration-time guard).
- **Docs**: `OPERATIONAL_CONTRACTS.md` gains a `_meta` namespace
  section.
- **Tests**: new `tests/test_meta_tool_disable.py` (or extension
  to an existing MCP-build test) for the smoke + filter behaviour.
- **Deps**: no version changes. Existing `fastmcp>=3.2,<4` floor
  is already the right one; this change makes us actually compatible
  with it.
- **Downstream**: a2web (and any other consumer) drops any local
  `fastmcp<3.0` workaround pin on next a2kit release.

### Explicitly out of scope (separate changes)

Round-6 also raised six other items. None are bundled here; each
is large enough to design and test independently:

- **`@app.async_resource` decorator** (round-5 gap 1) — eliminates
  hand-rolled lazy-singleton boilerplate in apps. Touches
  `app-singletons` + `lazy-init-resources` specs; deserves its own
  change.
- **Ambient `ctx` via ContextVar** (round-5 gap 2) — request-scoped
  context binding. Cross-cuts `mcp-context-passthrough`,
  `request-scoped-di`, and CLI transport; non-trivial.
- **`app.testing.override(T, fake)`** (round-5 gap 3) — DI override
  API on the test client. Belongs with `in-process-test-client`
  + `di-container-package`.
- **`a2kit.Param` docstring-pull / verbosity** (round-5 gap 4) —
  router ergonomics; touches `router-conventions`
  + `tool-description-contract`.
- **`client.call(..., wire=True)` / wire-payload inspection**
  (round-6 friction 2) — extends `in-process-test-client` to
  expose formatter-encoded output for assertions against
  `type-driven-format-routing` behaviour.
- **Component versioning (`@v1` keys) surface** — FastMCP 3 supports
  per-tool version specs; deferred until a2kit has a concrete
  versioning policy for its own tool surface.

These are noted so the round-6 reporter can see they're tracked,
but each warrants its own proposal.
