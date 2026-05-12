## Context

`build_mcp_server` (`src/a2kit/packages/mcp/server.py`) builds a
`FastMCP` server from an `App` by iterating tools, wrapping them
with router/dispatch/LDD layers, and registering each via
`FunctionTool.from_function(...)`. Tools whose resolved name starts
with `_RESERVED_TOOL_NAME_PREFIX` (`_meta.`) are meant to be hidden
from `list_tools`. The current code marks them hidden by calling
`tool.disable()` on the per-tool instance immediately after
construction.

FastMCP 3.0 removed `Component.disable()` (the instance-level form)
in favour of `server.disable(*, names=, keys=, tags=, version=,
components=)` — a visibility-transform API that operates at the
server level. The deprecation is hard: calling `tool.disable()` on
3.x raises `NotImplementedError` with the migration in the message.

a2kit pins `fastmcp>=3.2,<4` in `pyproject.toml`. Reproduced locally
on `fastmcp 3.2.4`: every `App` configured with `health_tool=True`
(or any other `_meta.*` registration) crashes during
`build_mcp_server`. CLI consumers (`a2kit.run` without `serve`)
are unaffected because they never enter this path. The blast radius
is therefore "any consumer who runs `<app> serve`."

The reporter also noted a `FastMCPDeprecationWarning` from importing
`FunctionTool` via `fastmcp.tools.tool`; the canonical path in 3.x
is `fastmcp.tools.function_tool`. Same file, same line range.

## Goals / Non-Goals

**Goals:**

- `build_mcp_server` succeeds end-to-end on `fastmcp>=3.2,<4` with
  the existing `_meta.health` registration and any future
  `_meta.*` tools. The `health-probe` spec's "Hidden from tool
  listings by default" requirement is honoured.
- Remove the `FastMCPDeprecationWarning` from a2kit's import surface.
- A registration-time guard prevents a recurrence of the
  documentation gap: any user-registered tool whose resolved name
  starts with `_meta.` is rejected at `build_mcp_server` time (in
  addition to the existing decoration-time rejection, which catches
  the literal-name path but not dynamic registrations).
- One smoke test pins the contract: build a server with a `_meta`
  tool, assert it registers without raising, assert default
  `list_tools` excludes it, assert direct invocation by name
  still works.
- `OPERATIONAL_CONTRACTS.md` documents the `_meta.*` namespace
  end-to-end so the next consumer doesn't have to read source.

**Non-Goals:**

- Adding an `include_meta` opt-in to `list_tools` (the existing
  `health-probe` spec mentions it; the implementation is out of
  scope for this change — it's a feature, not a regression fix).
- Component versioning (`@v1` keys). FastMCP 3 supports it via
  `server.disable(version=...)` and friends; a2kit has no
  versioning policy for its tool surface yet.
- The round-5 ergonomic gaps (async_resource, ambient ctx,
  testing.override, Param verbosity). See proposal "Out of scope".
- Wire-payload inspection on `a2kit.testing.client` (round-6
  friction 2). Separate change.

## Decisions

### D1: Use `server.disable(tags={"_meta"})` once, post-loop

Three alternatives considered for the FastMCP 3 migration:

1. **Per-tool key**: `server.disable(keys={f"tool:{name}@"})` immediately
   after each `server.add_tool(tool)`. Direct translation of the old
   per-tool `tool.disable()`. The key format (`tool:<name>@`) is
   public per the error message but the `@` suffix encodes versioning
   we don't use; relying on the exact format is brittle.
2. **Per-tool name**: `server.disable(names={name})` after each add.
   Cleaner than keys; doesn't encode versioning concerns.
3. **Tag-based, single call**: `server.disable(tags={"_meta"})` once
   after the registration loop. The code already tags every `_meta.*`
   tool with `"_meta"` (line 311 of `server.py`); the selector is
   semantic, not lexical, and is self-extending — any future
   `_meta.foo` tool inherits the tag and gets hidden automatically.

Decision: option 3. Rationale: matches how FastMCP 3 wants
visibility transforms used (declarative, tag/criteria-based,
applied at server level), removes a per-tool branch from the
loop, and ties the contract to the `"_meta"` tag rather than to
the lexical prefix.

### D2: Migrate `FunctionTool` import path

Current: `from fastmcp.tools.tool import FunctionTool` →
`FastMCPDeprecationWarning` on import.

New: `from fastmcp.tools.function_tool import FunctionTool`.

No alternative considered — the deprecation message names the
target verbatim. Mechanical change.

### D3: Registration-time guard for user `_meta.*` tools

The existing `health-probe` spec says decoration-time rejection
covers user tools that try to claim `_meta.*` names. That works
for literal `@a2kit.read(name="_meta.x")` but not for dynamic
paths (router prefixes, metadata mutation, etc.). The
`build_mcp_server` loop is the last point where every tool's
resolved name is known, so guarding here is belt-and-braces.

Decision: in the loop, raise `ValueError` if a tool is `_meta.*`
but wasn't tagged as a2kit-internal. The current path infers
internal-vs-user only by name prefix; we'll attach a sentinel
(`a2kit_internal: True` in metadata extras) when a2kit's own
builders register `_meta.health`, and check for it at
registration time. User tools missing the sentinel but with a
`_meta.*` name → typed error pointing at the reserved namespace
docs.

Alternative considered: rely solely on the decoration-time guard
in `health-probe`. Rejected because the round-6 reporter
specifically asked whether app authors *could* register
`_meta.foo` — the answer should be "no, and the framework tells
you why at boot."

### D4: Smoke test scope

The smoke test must catch the exact `NotImplementedError`
regression. Scope:

1. Construct an `App` with `health_tool=True` + one ordinary
   read tool.
2. Call `build_mcp_server(app)` — must not raise.
3. Inspect the server's tool registry: `_meta.health` is present
   AND is marked disabled (via `server.disable(tags={"_meta"})`).
4. Inspect default `list_tools` output: `_meta.health` is absent.
5. Call `_meta.health` by exact name through the in-process test
   client: must succeed.
6. Construct an `App` registering a user tool with name
   `_meta.custom` via a path that bypasses decoration-time guard
   (e.g. monkey-patched metadata); `build_mcp_server` must raise
   `ValueError`.

Steps 5 and 6 share the test file. Total: one new test module,
~80 LOC.

### D5: OPERATIONAL_CONTRACTS.md prose

Add a `## The _meta.* tool namespace` section with four short
bullets:

- The `_meta.*` prefix is closed; a2kit reserves it for
  framework-internal protocol tools (e.g. `_meta.health`).
- On the MCP wire, `_meta.*` tools are excluded from default
  `list_tools` output via `server.disable(tags={"_meta"})`.
  They remain callable by exact name — clients with prior
  knowledge can still invoke them.
- On the CLI, `_meta.*` tools surface under `<app> _meta …`
  in `--help`. This split is deliberate: humans driving the
  CLI benefit from discovering health/diagnostic tools;
  agents driving MCP don't.
- App authors trying to register a `_meta.*` tool get a
  `ValueError` at decoration or registration time.

Target ≤200 words per round-6 ask.

## Risks / Trade-offs

- **Risk**: `server.disable(tags={"_meta"})` filters by tag, so any
  future tool tagged `"_meta"` is hidden whether the author intended
  it or not. → **Mitigation**: the `"_meta"` tag is set by
  a2kit's own code (`server.py:311`), not by user metadata. User
  `tags=` from decorators are unioned with `"_meta"` only when
  `is_meta` is true (i.e., the name already matches the reserved
  prefix). No user-facing surface adds the tag.

- **Risk**: the in-loop guard (D3) breaks any consumer who was
  illicitly registering `_meta.foo` and depending on it working.
  → **Mitigation**: the `health-probe` spec already promises this
  rejection at decoration time; we're closing a hole, not adding
  a new restriction. Search showed no such usage in a2web (the
  only known external consumer).

- **Trade-off**: tag-based vs. key/name-based disable. Tags are
  semantically cleaner but require the registration order to be
  "register all, then disable" — i.e., the disable call moves out
  of the per-tool loop. Acceptable; the result is fewer lines and
  one fewer per-iteration branch.

- **Behaviour clarification**: FastMCP-3's `server.disable()` blocks
  both `list_tools` enumeration AND `call_tool` invocation — there
  is no "hidden-but-callable-by-name" mode on the MCP wire. CLI
  invocations bypass the MCP wire (they iterate `app.tools()`
  directly), so `<app> _meta health` keeps working; MCP clients
  cannot reach `_meta.*` tools at all. This is the contract we
  document.

## Release

Land, run CI, cut `v0.28.1`. No migration shim, no compat
fallback, no deprecation cycle — the prior code path was a
100% crash, and a2kit pins `fastmcp>=3.2,<4`, so there is no
prior-behaviour cohort to preserve.

## Open Questions

- Does `server.disable(tags={"_meta"})` need to be invoked before
  or after `server.add_middleware(...)` calls? Empirically these
  are independent (visibility transforms aren't middleware), but
  the test should pin the ordering we ship with.
- Should we file the upstream FastMCP deprecation-warning fix
  as a separate task or treat it as part of this change? Treating
  as part of this change for now (one PR, one call site).
