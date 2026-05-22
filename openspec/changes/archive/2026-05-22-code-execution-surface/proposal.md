## Why

a2kit tools today reach humans (CLI) and agents (MCP) one call at a
time. Agents pay a large token cost: every tool definition is loaded
into context up front, and every intermediate result is shuttled back
through the model. The agentic ecosystem converged on a fix — running
agent-authored code against tools instead of calling them one-by-one
(Anthropic's "code execution with MCP" reports ~98.7% token reduction
on a reference workflow). `docs/VISION.md` makes code execution a
**bundled surface**: every a2kit author gets it for free. The spike
in `docs/SPIKE_CODE_EXEC_DI.md` (passed) proved FastMCP's `CodeMode`
transform runs over a2kit's connection-scoped, DI-wired tools with
zero framework changes. This change turns that proven spike into a
shipped, capability-gated, toggleable surface.

## What Changes

- **BREAKING.** a2kit MCP servers expose code execution **on by
  default**. Adopting FastMCP's `CodeMode` transform **collapses the
  listed tool catalog** into discovery + execute meta-tools
  (`search`, `get_schema`, `execute`); real tools remain callable by
  name but no longer appear in `list_tools`. Existing consumers
  (a2web, a2atlassian, a2db, a2sdlc) must opt out or adopt the new
  surface — re-validation per ADR 0005.
- A single global **`execute`** tool runs agent-authored Python in a
  sandbox; its `call_tool(name, params)` reaches every tool the
  server holds, carrying a2kit's per-call connection scope and DI.
- **Capability-gating** — the sandbox may only reach tools permitted
  by a2kit's transport-neutral semantic flags (`destructive`,
  `open_world`, `visibility`). Stock `CodeMode` exposes everything
  indiscriminately; a2kit gates `destructive` tools behind an
  explicit grant.
- A **`--code-mode-off`** toggle on `serve` disables the surface
  (load-bearing for the future MCP gateway — backends run code mode
  off, the gateway holds the sole code-mode tool).
- **Per-surface exposure** — code execution is available on the CLI
  (one global subcommand) and on local + remote MCP. It is **never**
  exposed on the REST surface.
- **`pydantic-monty`** is packaged as a lazy optional dependency
  behind a new `a2kit[code-mode]` extra, confined to a new
  lazily-imported `a2kit.packages.*` module so `import a2kit` stays
  under the 100 ms cold-start budget.
- A **new ADR** records the adoption of FastMCP's `experimental`
  `CodeMode` and the capability-gating model.

## Capabilities

### New Capabilities

- `code-execution`: the bundled sandboxed code-execution surface —
  discovery + `execute` meta-tools adopted from FastMCP `CodeMode`,
  capability-gating by a2kit semantic flags, the `--code-mode-off`
  toggle, per-surface exposure rules (CLI + MCP, never REST), and the
  lazy-imported optional-dependency packaging.

### Modified Capabilities

<!-- None. Code execution is additive; it reads existing semantic
flags but changes no existing requirement. The catalog-collapse
behaviour is new behaviour of the new capability, not a modified
requirement of an existing one. -->

## Impact

- **New optional dependency** `pydantic-monty`, exposed via a new
  `a2kit[code-mode]` extra. Lazily imported; absent from the default
  install and from the cold-start path.
- **New package module** under `a2kit.packages.*` (name decided in
  design.md) — the one place `pydantic-monty` and FastMCP's
  `experimental` `CodeMode` are imported.
- **`build_mcp_server` / `serve` wiring** — install the `CodeMode`
  transform when code mode is on; honour `--code-mode-off`.
- **CLI builder** — add the global code-mode subcommand.
- **New ADR** — adoption of FastMCP `experimental` `CodeMode` +
  capability-gating model + the `fastmcp<4` churn watch.
- **FastMCP `experimental` namespace** — accepted API-churn risk;
  tracked against the `fastmcp<4` pin.
- Sibling changes that follow (not in this change): the REST surface
  and the remote-CLI client.
