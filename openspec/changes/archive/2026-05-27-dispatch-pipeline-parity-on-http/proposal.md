## Why

The transport-neutral `DISPATCH_PIPELINE` exists and MCP folds it per tool, but HTTP doesn't — instead, `packages/http/build.py` reaches into `_run_authorize_gate` via its own per-route wrapper (`_apply_authorize_gate`) and re-implements typed-error rendering as FastAPI exception handlers. That drift produces three observable smells the 2026-05-27 structural audit names directly:

- **S13** — `AuthorizeGateStage` duplicated on the HTTP path (per-route wrapper instead of pipeline stage).
- **S11** — HTTP has no equivalent of the MCP error-rendering stage; the typed `AppError` → wire mapping is re-derived in `_install_typed_error_handlers` instead of reading the canonical `_render_state` side-channel that `ErrorEnvelopeStage` populates.
- **R13** (post-mortem) — both surfaces hand-roll lazy-import substrate-type resolvers that already exist canonically in `packages/dispatch/substrate.py`.

ADR-0019 already established the pipeline as the transport-neutral seam. Finishing the job on HTTP closes the divergence before a third substrate makes it three-way drift.

## What Changes

- HTTP projection tools fold `DISPATCH_PIPELINE` per tool, the same way MCP does. `_apply_authorize_gate` is deleted; `AuthorizeGateStage` runs from the pipeline.
- A new `HttpErrorRenderStage` appends after the pipeline on the HTTP path, symmetric to the existing `McpErrorRenderStage`. It reads `_render_state` populated by `ErrorEnvelopeStage` and returns a `JSONResponse` (or raises a FastAPI-shaped exception that the existing exception-handler stack turns into one). `_install_typed_error_handlers` shrinks to a thin fallback for non-AppError unexpected exceptions.
- Principal extraction stays at the HTTP wire layer (FastAPI Security guard / `_install_auth_middlewares`). The wire layer's only new responsibility is calling `request_scope.publish(principal)` so `AuthorizeGateStage` and `DispatchHookStage` see it as a seeded scope value — the same bridge MCP's `PrincipalMiddleware` already uses.
- The "substrate <-> pipeline bridge" pattern is documented in `design.md` as the agreed contract: `request_scope` carries per-call seeds in; `_render_state` carries per-call error envelopes out. No new Protocol abstraction — just made explicit.

Explicitly NOT in scope:
- Generic `RenderStage` in the pipeline (success-path rendering stays at the wire layer; substrate-native types like `StreamingResponse` and MCP `Content` blocks would force the stage to be a no-op).
- Lifting MCP's `FormatRoutingMiddleware`, `ListViewMiddleware`, or `GuardsMiddleware` into the pipeline (they legitimately operate on FastMCP wire shapes).
- A `SubstrateBridge` Protocol or third-substrate accommodation (premature with one user).

## Capabilities

### New Capabilities
- `substrate-pipeline-bridge`: documents the contract between substrate adapters and the dispatch pipeline — the two ContextVar side-channels (`request_scope`, `_render_state`), what each substrate must seed before folding the pipeline, what each must read after the pipeline returns.

### Modified Capabilities
- `dispatch-pipeline`: HTTP now folds the pipeline; previously only CLI and MCP did. AuthorizeGateStage's pre-condition (`request_scope` must carry the Principal) is restated as a substrate-bridge invariant rather than transport-specific behaviour.
- `http-surface`: projection tool installation goes through `fold_pipeline` per tool. `_apply_authorize_gate` deleted from the surface; the gate runs from the pipeline.
- `error-envelope-rendering`: HTTP adopts the side-channel pattern. `_install_typed_error_handlers` becomes a fallback for genuinely-unexpected exceptions only; the typed `AppError` path flows through `ErrorEnvelopeStage` (populates `_render_state`) → `HttpErrorRenderStage` (reads it, renders to `JSONResponse`).
- `principal-bridge`: HTTP's middleware-side principal extraction publishes through `request_scope.publish(principal)`, matching MCP's `PrincipalMiddleware` pattern. The bridge is the single seam between substrate principal extraction and pipeline-stage principal use.

## Impact

- **Code**: `src/a2kit/packages/http/build.py` (largest delta — fold pipeline per tool, delete `_apply_authorize_gate`, shrink `_install_typed_error_handlers`). New `src/a2kit/packages/http/_error_render_stage.py` (small). New `src/a2kit/packages/http/_principal_middleware.py` (small, mirror of MCP's). Touches `src/a2kit/packages/dispatch/__init__.py` if `HttpErrorRenderStage` is exposed at the front door.
- **Tests**: HTTP path needs the regression suite MCP already has — authorize-gate per principal kind, error envelope shape across all `AppError` subclasses, principal seeded vs missing. New side-channel-contract capability test (`tests/capabilities/substrate_pipeline_bridge/`) asserts every registered substrate seeds `request_scope` before `fold_pipeline` and reads `_render_state` after.
- **Wire shape**: HTTP error responses MUST stay byte-equivalent to today's output for all currently-tested `AppError` subclasses (no consumer-visible change). The change is purely internal plumbing.
- **DI semantics**: zero observable change. Today both transports route through the same `_run_authorize_gate(authorize, container)` helper, which opens its own `call_scope` and resolves deps; `test_authorize_di_parity.py` proves allow/deny + DI parity holds before the refactor. S13's "drift risk" is structural (two code paths with the same job), not a current behavioural gap.
- **Cold start**: unchanged — pipeline stages already imported by MCP.
- **Dependencies**: none added.
- **Risk**: HTTP error-render regression and authorize-DI-scope behaviour change. Both have well-defined test surfaces; the design doc enumerates each.
