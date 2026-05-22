## Context

`docs/VISION.md` makes code execution a bundled a2kit surface. The
spike `docs/SPIKE_CODE_EXEC_DI.md` (passed) proved FastMCP 3.2's
`experimental.transforms.CodeMode` runs over a2kit's
connection-scoped, DI-wired tools with **zero framework changes** —
`build_mcp_server(app)` + `server.add_transform(CodeMode())` already
works end to end, including per-call connection resolution, DI, list
middleware, and structured results into the sandbox.

So feasibility is settled. This change is the productisation: turn
the bare transform into a default-on, capability-gated, toggleable
surface, packaged within a2kit's cold-start and module-layout
discipline.

Constraints that bound the design:

- `import a2kit` must stay under 100 ms — `pydantic-monty` and
  FastMCP `experimental` must be lazily imported (mirrors how
  `a2kit.packages.mcp` confines `fastmcp`).
- a2kit ships no redundant surfaces and no backward-compat shims
  (`AGENTS.md`).
- The semantic-flag vocabulary (`destructive`, `open_world`,
  `visibility`) is the transport-neutral gate input (ADR 0003).
- FastMCP `CodeMode` **collapses** the listed catalog — after the
  transform, `list_tools` returns only `search` / `get_schema` /
  `execute`. Real tools stay callable by name but are not listed.

## Goals / Non-Goals

**Goals:**

- Ship code execution as a default-on a2kit surface: adopt FastMCP
  `CodeMode`, do not reimplement it.
- Capability-gate the sandbox by a2kit's semantic flags — the real
  a2kit value-add over stock `CodeMode`.
- A `--code-mode-off` toggle (load-bearing for the future gateway).
- Expose on CLI + local/remote MCP; record "never REST" as a
  standing constraint.
- Package `pydantic-monty` as a lazy optional dependency within the
  module-layout and cold-start discipline.

**Non-Goals:**

- The REST surface and the remote-CLI client (sibling changes).
- The code-mode gateway (future; this change only delivers the
  `--code-mode-off` toggle it will depend on).
- A custom sandbox runtime — Monty via FastMCP is adopted as-is.
- Custom a2kit discovery tools — FastMCP's `search` / `get_schema`
  defaults are used.
- Gating *transitive* tool reach (a non-destructive tool calling a
  destructive one in its own body) — the gate governs *direct*
  sandbox reach only.

## Decisions

### D1 — New package `a2kit.packages.codemode`

The single home for FastMCP `experimental` `CodeMode` and
`pydantic-monty` imports, mirroring how `a2kit.packages.mcp` is the
one place `fastmcp` is imported. Nothing else in the tree imports
either dependency. This package is the swap point if FastMCP's
`experimental` API churns or Monty is replaced.

### D2 — Adopt `CodeMode`, subclass only for the gate

Per VISION principle 7 (lean on mature SDKs), a2kit does **not**
reimplement the transform. It ships `A2kitCodeMode(CodeMode)` that
overrides only catalog access to apply capability-gating. Sandbox
runtime, discovery tools, the `call_tool` bridge, resource limits
are inherited unchanged. _Alternative — a from-scratch transform:
rejected; the spike proved FastMCP's works, and reimplementing
forfeits the principle-7 bet._

### D3 — Capability-gating at the catalog, operator-controlled

`CodeMode` reads its tool set through `CatalogTransform`'s
auth-filtered catalog; both the discovery tools and `execute`'s
`call_tool` consult it. Filtering that catalog gates discovery and
execution in one place.

`A2kitCodeMode` filters the catalog by the `A2KitMeta` already
stamped onto every tool's `meta["a2kit"]` by `build_mcp_server`:

- `visibility != "all"` tools are already absent from the MCP
  surface — naturally excluded.
- `destructive` tools are **excluded by default**. The grant is an
  **operator-side** setting (`serve --code-mode-allow-destructive`,
  mirrored in config), never a per-call argument — an agent must not
  be able to grant itself destructive reach.
- `open_world` is informational, not a gate.

_Alternative — a per-call `allow_destructive` param on `execute`:
rejected; it lets the agent defeat its own gate._

### D4 — Toggle: `serve --code-mode-off`

`build_mcp_server` gains `code_mode: bool = True`; `serve` maps
`--code-mode-off` to `code_mode=False`, which skips installing the
transform. Default-on satisfies VISION principle 1. The CLI
code-mode subcommand (D6) is always present — it is local and
single-user; the toggle exists for the MCP wire and the gateway
backend story.

### D5 — Wiring into `build_mcp_server`

After the tool-registration loop and before returning, when
`code_mode` is on, install `A2kitCodeMode(...)` via
`server.add_transform(...)`. `_meta.*` tools stay excluded as
today. This is the only change to `build_mcp_server`'s body beyond
the new parameter.

### D6 — CLI: a global `code` subcommand

The CLI gains one global subcommand (`<app> code`) that accepts
Python source (positional, `--file`, or stdin) and runs it through
the same sandbox and the same capability gate, with
`call_tool(name, params)` in scope. It mirrors the MCP `execute`
tool so behaviour is identical across the two surfaces.

### D7 — "Never REST" as a standing requirement

The REST surface does not exist yet. This change writes the
prohibition into the `code-execution` spec as a requirement so the
future REST change is bound by it. No REST code is touched here.

### D8 — ADR 0013

A new ADR records: adoption of FastMCP `experimental` `CodeMode`,
the operator-controlled capability-gating model, the default-on
catalog-collapse as an accepted BREAKING change, and the
`fastmcp<4` API-churn watch. Pairs with VISION.md and the spike.

## Risks / Trade-offs

- **FastMCP `experimental` API churn** → confined to
  `a2kit.packages.codemode` (one import site); pinned `fastmcp<4`;
  the package is the documented swap point.
- **`pydantic-monty` is 0.0.x / immature** → isolated behind the
  `SandboxProvider` protocol and the `a2kit[code-mode]` extra; pin a
  known-good version; non-code-mode installs are unaffected.
- **Default-on collapses the listed catalog — BREAKING for existing
  consumers** → mark BREAKING; CHANGELOG migration row; ADR 0005
  re-validation; `--code-mode-off` is a one-flag opt-out; `search`
  keeps real tools discoverable.
- **The `get_tool_catalog` override point may be awkward**
  (`CatalogTransform` has re-entrancy machinery) → **resolved during
  apply**: `CatalogTransform.get_tool_catalog` is a plain public
  async method; both the discovery tools and `execute`'s `call_tool`
  route through it, so overriding it gates discovery and execution
  in one place. No fallback needed. Empirically re-confirmed by the
  apply-phase tests, which run against the gated `A2kitCodeMode`.
- **Transitive destructive reach** (a permitted tool invokes a
  destructive one internally) → out of gate scope by decision D3;
  documented as accepted.
- **Cold-start regression** → `a2kit.packages.codemode` is imported
  only on the `build_mcp_server` / `serve` / `code`-subcommand path;
  a test asserts `import a2kit` does not pull it.

## Migration Plan

Additive: a new package, a new `a2kit[code-mode]` extra, a new ADR.
No existing surface is renamed or removed. The one behaviour shift
is the default-on catalog collapse — carried as a CHANGELOG
migration row naming `--code-mode-off` as the opt-out. Rollback for
any consumer is the single `--code-mode-off` flag.

## Open Questions

- A config/env form of the toggle, for servers that are *always*
  gateway backends (beyond the per-invocation `serve` flag).
- Whether a finer destructive-grant model (per-tool allowlist) is
  ever needed beyond the binary operator switch.
- a2kit-specific discovery tools vs FastMCP defaults — deferred
  until a concrete need.
- `connection` ergonomics inside the sandbox (the agent repeats
  `connection` in every `call_tool`) — deferred.
