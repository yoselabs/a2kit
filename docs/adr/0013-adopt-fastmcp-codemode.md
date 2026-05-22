---
id: "0013"
status: accepted
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: []
superseded_by: null
tags: [code-execution, mcp, fastmcp, sandbox, surface]
deciders: [Denis Tomilin]
---

# ADR 0013: Adopt FastMCP `experimental` `CodeMode` for the bundled code-execution surface

## Status

Accepted, 2026-05-22. Implements the code-execution surface of
`docs/VISION.md`. Pairs with the spike `docs/SPIKE_CODE_EXEC_DI.md`
and the OpenSpec change `code-execution-surface`. The surface
shipped — `a2kit.packages.codemode` is in the tree.

## Summary

In the context of a2kit's bundled code-execution surface, facing the
choice between building a sandboxed code-execution transform from
scratch and adopting FastMCP 3.2's `experimental.transforms.CodeMode`,
we decided to adopt FastMCP's `CodeMode` — subclassed as
`A2kitCodeMode` only to add capability-gating — and against a
from-scratch implementation, to achieve a proven sandbox, discovery
tools, and tool-callback bridge at near-zero framework cost (the
spike confirmed it carries a2kit's connection-scoped DI unchanged),
accepting a dependency on FastMCP's `experimental` namespace
(API-churn risk, watched against the `fastmcp<4` pin) and a
default-on catalog-collapse that is a BREAKING change for existing
consumers, opt-out via `--code-mode-off`.

## The problem

`docs/VISION.md` makes code execution a bundled surface: every a2kit
author gets a token-efficient, agent-authored-code path over their
tools without writing anything. The implementation question is
whether to build that surface or adopt one.

FastMCP 3.2 ships `experimental.transforms.CodeMode`: a transform
that collapses the listed tool catalog into `search` / `get_schema` /
`execute` meta-tools and runs agent-authored Python in a
`pydantic-monty` sandbox, with `call_tool(name, params)` bridged back
through `ctx.fastmcp.call_tool`.

The spike (`docs/SPIKE_CODE_EXEC_DI.md`) proved this works over
a2kit's connection-scoped, DI-wired tools with zero framework
changes — the per-call dispatch hook and DI run on the nested
`call_tool` exactly as on a direct MCP call. So feasibility is not
the question. The question is build-vs-adopt, and how to make the
adopted surface safe and toggleable.

## What we considered (and why this one)

### Option 1: Adopt FastMCP `CodeMode`, subclass for the gate (chosen)

a2kit ships `A2kitCodeMode(CodeMode)` — FastMCP's transform plus one
override (`get_tool_catalog`) that applies capability-gating. The
sandbox runtime, discovery tools, the `call_tool` bridge, and
resource limits are inherited unchanged.

Why it wins:

- **VISION principle 7 — lean on mature SDKs.** The spike already
  proved the FastMCP path; reimplementing forfeits that and doubles
  the maintained surface.
- **Single override point.** `CatalogTransform.get_tool_catalog` is
  the one method both discovery and `execute` route through;
  overriding it gates discovery and execution together.
- **`pydantic-monty` is the blessed sandbox.** It is the same Monty
  lineage a limited code-execution sandbox was once built on here;
  the `SandboxProvider` protocol keeps it swappable later.

### Option 2: A from-scratch code-execution transform

Rejected. It would duplicate a proven implementation, own the
sandbox-callback boundary outright, and contradict principle 7. The
only thing a2kit genuinely needs to add — capability-gating — is a
small subclass on top of Option 1.

### Option 3: Make code execution opt-in (default off)

Rejected as the default. VISION principle 1 is zero-config: every
surface is on unless turned off. Code execution is a surface.
`--code-mode-off` is the opt-out, and it is load-bearing for the
future MCP gateway (backends run code mode off; the gateway holds
the sole code-mode tool). The cost — a default-on catalog-collapse
that is BREAKING for existing consumers — is accepted: a2kit is
alpha, consumers re-validate per release (ADR 0005), and the opt-out
is a single flag.

## The decision

a2kit adopts FastMCP's `experimental` `CodeMode`. The code-execution
surface is:

- **`A2kitCodeMode`** — `CodeMode` subclassed to override
  `get_tool_catalog`, filtering the sandbox-reachable catalog.
- **Capability-gating, operator-controlled.** Tools flagged
  `destructive` are excluded from the sandbox catalog by default —
  not discoverable, not callable from `execute`. The grant is an
  operator-side decision (`serve --code-mode-allow-destructive`),
  never a per-call argument; the agent cannot self-grant. Tools with
  `visibility != "all"` are already absent from the MCP surface and
  so naturally excluded.
- **Default-on, with `--code-mode-off`.** `build_mcp_server` gains
  `code_mode: bool = True`. Installing the transform collapses the
  listed catalog into `search` / `get_schema` / `execute`; real
  tools stay callable by name. `--code-mode-off` skips the transform.
- **Per-surface exposure.** Code execution is exposed on local +
  remote MCP, and on the CLI as a global `code` subcommand. It is
  **never** exposed on the REST surface — recorded as a binding
  requirement in the `code-execution` spec for the future REST change.
- **Lazy, optional dependency.** `pydantic-monty` and FastMCP's
  `experimental` `CodeMode` are imported only from
  `a2kit.packages.codemode`, off the `import a2kit` cold-start path,
  installable via the `a2kit[code-mode]` extra. The CLI `code`
  subcommand is registered **only when that extra is installed** —
  `find_spec` checks for `pydantic-monty` without importing it — so a
  lean CLI install carries no sandbox dependency and advertises no
  command it cannot run.

## Consequences

### Positive

- A proven code-execution surface for near-zero framework cost.
- Capability-gating gives a2kit a real safety property FastMCP's
  stock `CodeMode` lacks.
- One toggle (`--code-mode-off`) cleanly opts a server out — and is
  the mechanism the future code-mode gateway depends on.
- Cold-start budget preserved: the sandbox runtime never loads on
  `import a2kit`.

### Negative

- **BREAKING for existing consumers.** Default-on collapses the
  listed catalog; agents that enumerate `list_tools` see only the
  meta-tools until they adopt code mode or pass `--code-mode-off`.
  Carried as a `CHANGELOG` migration row.
- **`experimental`-namespace dependency.** `CodeMode` may change API
  before it graduates; `pydantic-monty` is a `0.0.x` release.
  Confined to `a2kit.packages.codemode` as the single swap point.
- **Transitive destructive reach is not gated.** The gate governs
  *direct* sandbox reach; a permitted tool that calls a destructive
  one in its own body is out of scope.

### Re-evaluation triggers

- FastMCP graduates `CodeMode` out of `experimental`, or its API
  changes — re-pin and re-validate `a2kit.packages.codemode`.
- A FastMCP 4 upgrade — the `fastmcp<4` pin is the explicit gate.
- A finer destructive-grant model (per-tool allowlist) is filed as a
  real consumer need beyond the binary operator switch.

Any of these triggers an ADR amending or superseding this one.

## References

- `docs/VISION.md` — the code-execution surface and its principles.
- `docs/SPIKE_CODE_EXEC_DI.md` — the passing feasibility spike.
- OpenSpec change `code-execution-surface` — proposal, design, spec,
  tasks.
- ADR 0003 — the semantic-flag vocabulary the gate reads.
- ADR 0005 — consumer-feedback / re-validation doctrine.
- ADR 0012 — MCP deployment topology; the code-mode gateway will
  pair with a re-evaluation of it.
