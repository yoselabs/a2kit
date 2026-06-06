## Why

The MCP protocol lets a server advertise **server-level natural-language
instructions** to connecting clients/agents — a short description of what
the server is for and how to use its tools, surfaced by the host
alongside the tool catalog. FastMCP supports this directly via the
`instructions=` parameter on `FastMCP.__init__`.

a2kit's `McpConfig` (`src/a2kit/config.py`) carries `structured_output`
but has **no `instructions` field**, and `build_mcp_server`
(`src/a2kit/packages/mcp/server.py:284`) constructs the FastMCP server as
`FastMCP(name=runtime.name, **fastmcp_kwargs)` without ever threading any
config-supplied instructions into it. So a consumer rebuilding on
a2kit-native (a2kay) has **no first-class way to give MCP clients
server-level guidance** — they can only reach the raw `FastMCP` after
build via the escape hatch, which is undiscoverable and bypasses the
typed config surface.

This is **friction #6** from the a2kay feedback round (ADR 0028: "No
`McpConfig.instructions`" / "per-surface config exists but `bind()`
doesn't read all of it") and is a **Wave 3, additive** item in
`docs/SURFACE_ARCHITECTURE.md` §7 ("`McpConfig.instructions` threaded by
`McpSurface.bind`").

## What Changes

Add a `instructions` field to `McpConfig` and have the MCP server builder
(today's `McpSurface.bind` equivalent, `build_mcp_server`) thread it into
the FastMCP server constructor's `instructions=` parameter.

- **`src/a2kit/config.py`** — add `McpConfig.instructions: str | None`,
  default `None`. Consumer-owned, settable via env
  `A2KIT_MCP__INSTRUCTIONS` per the ADR 0022 provider chain (env beats
  code), consistent with `structured_output`.
- **`src/a2kit/packages/mcp/server.py`** — at FastMCP construction
  (`:284`), pass `instructions=runtime.config.mcp.instructions` (read off
  the resolved config the builder already holds via
  `runtime.config.mcp`). When `None`/absent, the parameter is omitted (or
  passed as `None`), so FastMCP's default-instructions behavior is
  preserved byte-for-byte. An explicit `fastmcp_kwargs["instructions"]`
  supplied by the caller continues to win (the escape hatch is not
  overridden).

## Capabilities

### Modified Capabilities

- `runtime-config` — `McpConfig` gains an `instructions: str | None`
  field (consumer-owned, env-overridable) and the MCP server build
  threads it into the FastMCP server's `instructions=` so connecting MCP
  clients see server-level guidance. `runtime-config` is the capability
  that owns `McpConfig` and the wire-effect contracts of its fields
  (cf. the existing `McpConfig.structured_output controls success-path
  wire shape` requirement, which likewise spans both the field and its
  server-side effect).

## Impact

- Affected code: `src/a2kit/config.py` (one new field),
  `src/a2kit/packages/mcp/server.py` (one constructor kwarg at `:284`).
- **ADDITIVE, non-breaking.** Default `None` preserves today's behavior:
  no instructions field today → no instructions passed to FastMCP →
  unchanged server. No existing field, env var, or wire shape changes.
- a2kay (and any consumer) can now set
  `mcp=McpConfig(instructions="…")` (or `A2KIT_MCP__INSTRUCTIONS=…`) to
  advertise server-level guidance to MCP hosts through the typed config
  surface instead of the raw-FastMCP escape hatch.

## Non-goals

- **Not** per-tool descriptions — those are the tool's own
  `description` / docstring (separate contracts). This is the
  *server*-level `instructions` string only.
- **Not** the unified `surfaces` axis or any other Wave 2 breaking
  change — this is a standalone additive Wave 3 item.
- **Not** changing or removing the raw-FastMCP escape hatch
  (`fastmcp_kwargs`); a caller-supplied `instructions=` still wins.
- **Not** adding `instructions` to the HTTP or CLI surfaces (MCP-only
  protocol concept).
