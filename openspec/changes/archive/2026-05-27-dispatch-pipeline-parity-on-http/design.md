## Context

`DISPATCH_PIPELINE` (`src/a2kit/packages/dispatch/pipeline.py`) is the transport-neutral per-tool middleware chain. Today it's folded by the CLI (`cli/runtime.py`) and the MCP server build (`mcp/server.py:_build_one_tool`). The HTTP path (`http/build.py:build_http_app`) doesn't fold it — instead, it calls `install_substrate_signature` to get a substrate-shaped wrapper, then layers on `_apply_authorize_gate` (a hand-rolled wrapper around `_run_authorize_gate`) and `_install_typed_error_handlers` (FastAPI exception handlers that re-derive the typed-error → HTTP-status mapping that `ErrorEnvelopeStage` + `McpErrorRenderStage` already cover for MCP).

The audit (`STRUCTURE_ISSUES.md` 2026-05-27) names three smells from this divergence: **S13** (AuthorizeGate duplicated), **S11** (HTTP missing render stage), and the post-mortem note on **R13** (substrates re-rolling helpers that exist canonically).

Four independent agents (framework precedent / first-principles / a2kit-deep-read / anti-pattern) brainstormed this on 2026-05-27. Convergent findings:

- The pipeline IS the right transport-neutral seam (4/4).
- Wire concerns (CORS, content negotiation, streaming, FastMCP middleware, substrate-native types) stay substrate-side (4/4).
- The bridge between substrate adapters and pipeline stages is two **named ContextVars**: `request_scope` (in: per-call seeds) and `_render_state` (out: per-call error envelope) (3/4 explicit, 1/4 implicit).
- Authorization is **NOT cleanly one-sided** — principal *extraction* is wire (substrate-specific), gate *enforcement* is tool-call (pipeline-side). They must stay split (4/4, anti-pattern strongest).
- A generic `RenderStage` in the pipeline would break substrate-native return types (StreamingResponse, MCP Content blocks) and back-pressure (anti-pattern).

The half-built abstraction that wants to emerge: **one pipeline, sandwiched between two thin substrate adapters, communicating via two named ContextVar side-channels**.

## Goals / Non-Goals

**Goals:**
- HTTP projection-tool installation folds `DISPATCH_PIPELINE` per tool. `AuthorizeGateStage` runs from the pipeline on every transport (CLI, MCP, HTTP) by the same code path.
- Typed `AppError` rendering on HTTP flows through `ErrorEnvelopeStage` (populates `_render_state`) → `HttpErrorRenderStage` (reads it, renders `JSONResponse`), symmetric to MCP. `_install_typed_error_handlers` shrinks to handle non-AppError fallthrough only.
- The substrate-to-pipeline bridge is **documented as a contract**: two ContextVars (`request_scope` for inbound seeds, `_render_state` for outbound error envelopes), substrate seed/read responsibilities listed explicitly. A new capability spec (`substrate-pipeline-bridge`) captures it.
- Wire-shape of HTTP error responses is byte-equivalent to today's output (regression-tested).
- `_apply_authorize_gate` deletes. Single source of truth for authorize-gate behaviour.

**Non-Goals:**
- Generic `RenderStage` in the pipeline. Success-path rendering stays at the wire layer — MCP's `FormatRoutingMiddleware` stays where it is (it manipulates the FastMCP content channel post-call; pipeline can't see substrate-native shapes); HTTP gets nothing analogous in this change because FastAPI handles content negotiation.
- Lifting `ListViewMiddleware`, `GuardsMiddleware`, `FormatRoutingMiddleware`, or `PrincipalMiddleware` (the MCP-side one) into the pipeline. They legitimately operate at the FastMCP wire layer.
- Extracting a `SubstrateBridge` Protocol. Single user (HTTP needs to adopt the pattern) — speculative until a third substrate is real. The contract lives as documentation + capability test, not as a callable abstraction.
- Touching `install_substrate_signature` semantics. Signature splitting is per ADR-0020 and stays as-is.
- Touching CLI. CLI already folds the pipeline; no change.
- Reordering pipeline stages. Order is load-bearing (per existing tests); this change preserves it.

## Decisions

### Decision 1: Move `AuthorizeGateStage` ENFORCEMENT into the HTTP pipeline; keep Principal EXTRACTION at the wire layer.

The proposal's load-bearing question is "where does authorization live?" The adversary axis flagged this hardest: authorization has *two* phases — extracting the Principal from substrate-native auth (HTTP header, MCP context) and applying the gate against the tool's `authorize=` callable. Extraction must be substrate-specific (HTTP reads `Authorization:` header via FastAPI Security; MCP reads `Context.session.client.auth`); the gate is pure domain logic.

**Decision**: HTTP middleware extracts Principal and calls `request_scope.publish(principal)`. The pipeline's `AuthorizeGateStage` reads it from the request scope, exactly as on MCP today. `_apply_authorize_gate` deletes.

**Alternatives considered**:
- *Keep HTTP's per-route wrapper, just refactor it for clarity.* Rejected — perpetuates S13 drift.
- *Make AuthorizeGateStage extract Principal itself.* Rejected — pipeline can't import substrate types.
- *Move Principal extraction into a pipeline stage too.* Rejected — would require pipeline stages to receive raw substrate types (HTTP Request, FastMCP Context), violating transport-neutrality.

**Why this is safe** (revised 2026-05-27 after baseline-suite run): Today both HTTP and MCP route through the same `_run_authorize_gate(authorize, container)` helper, which opens its own `call_scope` and resolves the callable's deps. The `tests/packages/http/test_authorize_di_parity.py` suite (allow/deny × HTTP/MCP-fold = 4 cases) confirms allow/deny + DI-resolution behaviour is **identical today**. S13 is therefore **purely structural drift** (two code paths with the same job that WILL drift over time as the gate grows new concerns), not behavioural divergence. The refactor's value is preventing future regression, not fixing today-broken behaviour. The change is expected to have **zero observable wire delta**; the snapshot suite (`test_http_error_envelope_snapshot.py`, 8 cases) enforces that.

### Decision 2: Add `HttpErrorRenderStage`, symmetric to `McpErrorRenderStage`; shrink `_install_typed_error_handlers`.

Today HTTP re-derives `AppError → HTTP status + JSON body` in two places: per-call inside `_apply_authorize_gate`, and in `_install_typed_error_handlers` as a FastAPI exception handler. Both bypass `ErrorEnvelopeStage`'s `_render_state` side-channel.

**Decision**: Add `HttpErrorRenderStage` that runs after the pipeline (in the per-tool wrap, post-`fold_pipeline`), reads `_render_state` for the rendered envelope, and either returns the response directly or raises a FastAPI-native exception the existing handlers convert. `_install_typed_error_handlers` shrinks to non-AppError fallthrough (e.g. `RequestValidationError`, generic 500s).

**Alternatives considered**:
- *Generic `RenderStage` in the pipeline serving both error and success paths.* Rejected per anti-pattern axis (substrate-native types, streaming).
- *Keep FastAPI exception handlers as the only HTTP error path.* Rejected — defeats the symmetry, perpetuates S11.

**Wire-shape invariant**: The new path MUST produce the same JSON body and HTTP status code for every currently-tested `AppError` subclass. Regression suite enforces this.

### Decision 3: Document the bridge as `substrate-pipeline-bridge` capability spec; do NOT add a `SubstrateBridge` Protocol.

The four-agent brainstorm converged on "two ContextVars are the bridge." Making this a typed Protocol now is premature (one consumer to convert). But the contract needs to be **enforceable** — a future substrate must follow it.

**Decision**: A capability spec at `openspec/specs/substrate-pipeline-bridge/spec.md` documents the two ContextVars, who seeds what, who reads what, in what order. A capability test under `tests/capabilities/substrate_pipeline_bridge/` asserts every registered substrate (HTTP, MCP, CLI) honours the contract — specifically: the wire-side seed happens before the pipeline folds, and the wire-side read of `_render_state` happens after the pipeline raises.

**Alternatives considered**:
- *Extract a `SubstrateBridge(Protocol)` with `seed_scope(...)` / `render_error(...)` methods.* Rejected — speculative abstraction with one user.
- *Leave the contract as docstring convention.* Rejected — drift is exactly what produced S13/S11.

**Promotion path**: when a third substrate (gRPC, AGNTCY, queue-consumer) lands and the bridge is exercised three times, promote to a Protocol then. The capability test gives us the regression net to do so.

### Decision 4: Principal-publish on HTTP — a per-tool-wrap helper, NOT a middleware (revised 2026-05-27 after baseline).

**Initial assumption** (now superseded): a Starlette-style `_principal_middleware.py` would extract Principal once per request and publish to `request_scope`.

**What baseline revealed**: HTTP has TWO Principal sources today:
1. **API-key auth** (`packages/auth/api_key.py`): a Starlette ASGI middleware that already calls `request_scope.publish(principal)` itself. Today's wire-layer publish for API-key flows works correctly.
2. **FastAPI `Security(...)` guards** (e.g. `Annotated[Principal, Security(...)]`): FastAPI runs the Security dep AFTER all Starlette middlewares — the Principal lands as a route kwarg only inside the per-tool wrapper. No Starlette middleware can see it.

Therefore a single `_principal_middleware.py` cannot cover both paths. The kwarg-scraping logic that today lives inside `_apply_authorize_gate` is genuinely required for the FastAPI-Security path.

**Decision**: Extract the kwarg-scraping into a small `packages/http/_principal_publish.py` helper (`publish_principal_from_kwargs(kwargs) -> Token | None`). The per-tool wrapper in `build_http_app` calls it before `fold_pipeline` and resets in `finally`. The API-key middleware keeps publishing as it does today (no change there). Both seams write to `request_scope`; they're complementary, not duplicate (different auth paths, mutually exclusive per-request).

**Alternatives considered**:
- *Make a Starlette middleware that picks up FastAPI Security results.* Impossible — Starlette middlewares run outside FastAPI's dep resolution.
- *Use a FastAPI `dependencies=[Depends(_publish_principal)]` route-level dep.* Rejected — would require every projection-tool route to be re-registered with the dep, and Depends ordering vs the user's Security guard isn't guaranteed.
- *Move publish into `install_substrate_signature`.* Rejected — that's per ADR-0020 a signature-splitting concern; adding publish behaviour there couples two orthogonal jobs.

### Decision 5: Pipeline order and stage set are UNCHANGED.

The pipeline order is load-bearing (existing tests assert it). This change adds no new stages and reorders nothing. `HttpErrorRenderStage` lives in `packages/http/`, not in the pipeline — it's the HTTP-side read of `_render_state`, run by `build_http_app`, structurally identical to how `McpErrorRenderStage` runs on the MCP side.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| HTTP error responses change byte-shape under refactor | Snapshot test per `AppError` subclass before changing any code; assert byte-equality after. Roll back if any snapshot drifts. |
| `authorize=` callables that resolve DI dependencies behave differently on HTTP | Net-new behaviour, not a regression (HTTP just gets parity with MCP). Document in CHANGELOG under "Fixed". Tests cover authorized-allow / authorized-deny / authorize-raises across all principal kinds. |
| Pipeline folds on HTTP add per-request overhead (stage chain construction) | `fold_pipeline` happens at install time, not per request (same as MCP). Benchmark the HTTP request path before/after; assert no regression beyond noise. |
| `request_scope.publish(principal)` from middleware leaks across requests if reset is skipped | The publish/reset pattern is established in MCP's `PrincipalMiddleware`; mirror it exactly, including the `try`/`finally`. Capability test asserts the contextvar is reset post-request. |
| Future substrate author misses the bridge contract and skips `request_scope.publish` | Capability test enumerates registered substrates and asserts contract honour. New substrate without bridge wiring fails CI. |
| `HttpErrorRenderStage` and FastAPI's existing handler stack double-handle AppError | The render stage runs INSIDE the per-tool wrap and returns/raises before FastAPI's outer handlers see anything. The exception-handler stack handles only what escapes (non-AppError, framework-side validation, etc.). Test: AppError raised from tool body → single JSONResponse, never double-rendered. |
| Behaviour regression on `_meta.health` or other multi-tool MCP-specific endpoints | This change touches only the HTTP path; MCP path unchanged. Smoke-test MCP server build still passes existing tests. |

## Migration Plan

1. Land the proposal and capability spec first (no code change). CI gates on spec-drift caught.
2. Implement Decision 1 (Principal middleware + bridge) on HTTP. Add tests asserting `request_scope.publish` happens before pipeline. **HTTP error path unchanged at this stage.**
3. Implement Decision 2 (`HttpErrorRenderStage`) wired alongside existing `_install_typed_error_handlers`. New tests asserting side-channel path. Old handlers still cover; this is additive.
4. Switch HTTP projection-tool install to `fold_pipeline`. `_apply_authorize_gate` deletes.
5. Shrink `_install_typed_error_handlers` to non-AppError fallthrough. Verify all snapshot tests still byte-equal.
6. Capability test for `substrate-pipeline-bridge` lands and runs against all three substrates.

No rollback complexity — each step is additive until step 4. If step 4 regresses, revert that commit; pipeline-folding path is gone, old path is restored unchanged.

## Open Questions

- Does `_meta.health` need to run through the pipeline? Today it's a plain FastAPI route, not a projection tool. Default: leave as-is (it's a substrate-native liveness probe, not a tool). Confirm during implementation.
- Should `HttpErrorRenderStage` live in `packages/http/` or `packages/dispatch/`? `McpErrorRenderStage` lives in `packages/mcp/_wrappers.py`, so by symmetry the HTTP one lives in `packages/http/`. Confirm during implementation.
- Wire format for `RequestValidationError` from FastAPI body parsing — does it currently match a typed-error envelope shape or pass through FastAPI's default? Whatever it does today, preserve it. (Out of scope to change.)
