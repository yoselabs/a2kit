---
id: "0025"
status: accepted
date: 2026-05-27
last_reviewed: 2026-05-27
supersedes: []
superseded_by: null
tags: [architecture, dispatch, substrates, http, mcp]
deciders: [Denis Tomilin]
---

# ADR 0025: Substrate-to-pipeline bridge via two named ContextVars

## Status

Accepted, 2026-05-27. Implemented in change
`dispatch-pipeline-parity-on-http`.

## Summary

In the context of finishing what ADR 0019 started (a transport-neutral
`DISPATCH_PIPELINE` folded by every substrate adapter), facing the fact
that the HTTP path had drifted from the pipeline by hand-rolling
`_apply_authorize_gate` and `_install_typed_error_handlers` while MCP
and CLI consumed the pipeline directly, we decided for **a documented
two-ContextVar bridge contract** — `request_scope` for inbound typed
seeds (substrate → pipeline) and `_render_state` for outbound rendered
envelopes (pipeline → substrate) — and rejected **a typed
`SubstrateBridge(Protocol)` class** to achieve **closure of audit smells
S11 + S13, prevention of future drift between substrates, and a
substrate-onboarding contract that a third substrate (gRPC, AGNTCY,
queue consumer) can adopt unambiguously**, accepting **a defensive
capability-test enforcement instead of compile-time Protocol checks
(promotion to Protocol deferred until the contract has a third user)**.

## Context

ADR 0019 split `App` (compose-time) from `AppRuntime` (sealed) and
established `DISPATCH_PIPELINE` as the transport-neutral per-tool
middleware chain that the CLI and MCP adapters fold. The HTTP adapter
landed without folding the pipeline: `packages/http/build.py` carried
its own `_apply_authorize_gate` wrapper and `_install_typed_error_handlers`
that re-derived the `AppError → status` mapping inline. The 2026-05-27
structural audit (`STRUCTURE_ISSUES.md`) catalogued this as:

- **S11** — HTTP missing the typed-render-stage pattern present on MCP.
- **S13** — `AuthorizeGateStage` duplicated on HTTP (per-route wrapper
  vs pipeline stage).
- **R13** (post-mortem on the rego policy layer) — substrates re-rolling
  helpers already canonical in `packages/dispatch/`.

A four-axis parallel-agent brainstorm on 2026-05-27 (framework
precedent / first principles / a2kit deep-read / anti-pattern) reached
strong cross-confirmation that:

1. The pipeline IS the right transport-neutral seam (4/4 axes).
2. Wire concerns (CORS, content negotiation, streaming, format-routing)
   stay substrate-side (4/4).
3. The bridge between substrate adapters and pipeline stages should be
   **two named ContextVars** (3/4 explicit, 1/4 implicit).
4. Authorization splits: principal *extraction* is wire-specific, gate
   *enforcement* is tool-call (pipeline-side); they MUST stay split
   (4/4, anti-pattern axis strongest).
5. A generic `RenderStage` in the pipeline would break substrate-native
   return types (`StreamingResponse`, MCP `Content`) and back-pressure.

## Decision

**The substrate-to-pipeline bridge is two named ContextVars:
`a2kit.packages.context.request_scope` (inbound seeds) and
`a2kit.packages.dispatch._render_state` (outbound rendered envelopes).
No `SubstrateBridge` Protocol class is introduced at this time.**

Every substrate adapter SHALL:

1. Publish typed seeds (today: `Principal`) onto `request_scope` BEFORE
   folding the pipeline for a call.
2. Open `_render_state` around the call so `ErrorEnvelopeStage` has
   somewhere to write.
3. On `CapturedError` whose wrapped exception is an `AppError`, read the
   rendered envelope from `_render_state` via `get_rendered_error(exc)`
   and convert it to substrate-native wire shape.
4. Never re-derive the `AppError → kind → wire-shape` mapping. The
   prose + envelope-dict mapping lives once in `ErrorEnvelopeStage`;
   substrate-specific code (HTTP status, CLI exit code) lives in one
   helper per substrate.

The contract is enforced by capability tests under
`tests/capabilities/substrate_pipeline_bridge/`. Pipeline modules
(`packages/dispatch/`) SHALL NOT import `fastapi`, `starlette`, or
`fastmcp`; substrate adapters SHALL NOT bypass the named ContextVars to
reach into pipeline internals.

## Consequences

**Positive**:

- S11 closed: HTTP gains parity with MCP/CLI on the typed-render-stage
  pattern via `HttpErrorRenderStage`.
- S13 closed: `AuthorizeGateStage` runs from the pipeline on every
  substrate; `_apply_authorize_gate` deleted.
- Future-substrate onboarding has an unambiguous, testable contract.
- Zero behavioural delta on the wire (snapshot tests assert byte
  equivalence across every `AppError` subclass).

**Trade-offs**:

- Two ContextVars are easy to confuse with each other for a casual
  reader; the docs at `docs/dev/substrate-pipeline-bridge.md` and
  capability spec at
  `openspec/specs/substrate-pipeline-bridge/spec.md` are load-bearing.
- HTTP's per-tool wrap has nested `Container.call_scope` opens
  (substrate wrapper + `DispatchHookStage`). Both inherit
  `framework_seeds`; SCOPED instances are shared via the
  request-scope-published Container — correct but slightly wasteful.
  Fix is "task 1.6 of some change" (per the existing
  `install_substrate_signature` docstring) — deferred.
- Contract is type-system-invisible (no Protocol class). A future
  substrate author can violate the bridge without their IDE catching
  it; only the capability test does.

**Promotion path**:

When a third substrate exercises the bridge, the change introducing it
SHALL evaluate whether to extract a `SubstrateBridge(Protocol)` with
typed `seed_scope(wire)` / `render_error(envelope)` methods. The
capability test gives us the regression net to do so safely.

## Alternatives considered

- **Extract `SubstrateBridge(Protocol)` now.** Rejected: speculative
  abstraction with one user being onboarded; Protocol would add API
  surface without buying clarity. Deferred until a third substrate.
- **Generic `RenderStage` in the pipeline.** Rejected per anti-pattern
  axis: would preclude substrate-native return types (StreamingResponse,
  MCP Content blocks) and back-pressure. Each substrate's wire shape is
  legitimately substrate-specific; the pipeline produces a neutral
  envelope dict, substrates render.
- **Move `RenderedError.http_status` onto the shared dataclass.**
  Rejected: status code is HTTP-specific (gRPC and MCP map kinds
  differently). The substrate-side `http_status_for(exc)` helper
  decides for HTTP; CLI's `_cli_exit_for(exc)` decides for CLI.
- **Make every auth middleware publish to `request_scope` directly.**
  Rejected: couples auth implementations to dispatch internals. The
  substrate adapter owns the publish seam.
- **Use a FastAPI dependency `Depends(_publish_principal)` on every
  projection route.** Rejected: would require every projection-tool
  route to be re-registered with the dep, and Depends ordering vs the
  user's Security guard isn't guaranteed.

## References

- Change: `openspec/changes/dispatch-pipeline-parity-on-http/`
- Capability spec: `openspec/specs/substrate-pipeline-bridge/spec.md`
- Reference doc: `docs/dev/substrate-pipeline-bridge.md`
- ADR 0019: split app/runtime, dispatch pipeline is the neutral seam.
- ADR 0020: substrate signature splitting (parameter classification).
- `STRUCTURE_ISSUES.md` S11, S13, R13: audit smells closed.
- Four-axis parallel-agent brainstorm: 2026-05-27 (saved in change
  conversation; findings summarised in `design.md` Context).
