## Why

The auth wave landed `Principal` propagation but ended with two
threading paths:

1. **Contextvar**: a `_a2kit_request_principal` ContextVar is set by the
   substrate guard and read inside `DispatchHookStage` and
   `_run_authorize_gate`.
2. **DI scope**: `Principal` is written into the SCOPED container per
   the `principal-propagation` spec; tool bodies resolve it via type
   annotation.

`stages.py:173-175` reads the contextvar and re-seeds it into kwargs as
a defensive belt-and-braces. `stages.py:199-204` has a fallback:
container lookup OR contextvar OR re-inject. Two parallel paths;
neither is canonical. The coherence audit (2026-05-25) flagged this as
minor drift that will ossify if left.

Research finding from the same audit: Litestar-style scoped DI is the
lowest-regret pattern; signal/contextvar mechanisms are the most
regretted because they hide the data path.

This change collapses to one: DI scope is the source of truth; the
contextvar is removed (or kept only as the internal mechanism by which
the substrate adapter populates the DI scope, never read by stages).

## What Changes

- Remove the `_a2kit_request_principal` contextvar read from
  `DispatchHookStage.wrap()` (`stages.py:173-175`).
- Remove the contextvar fallback from `_run_authorize_gate`
  (`stages.py:196-204`); the gate resolves `Principal` from the DI
  scope only.
- Substrate adapters (MCP `PrincipalMiddleware`, FastAPI guard) write
  `Principal` into the per-call DI scope as today. The contextvar is
  either: (a) removed entirely, or (b) retained as an internal
  implementation detail of the substrate adapters (no stage reads it).
  Decided in design.md.
- Tool bodies and `authorize=` callables resolve `Principal` exclusively
  via DI. No code under `src/a2kit/packages/dispatch/` reads
  `_a2kit_request_principal`.
- The kwargs re-seed (`stages.py:173-175`) is removed; the DI resolver
  populates the body's `principal: Principal` parameter via the same
  per-call resolution path that handles every other typed dep.

## Capabilities

### Modified Capabilities

- `principal-propagation`: documents DI as the single resolution path;
  the contextvar is no longer a documented source. Existing scenarios
  remain valid (tool body resolves via type annotation).
- `dispatch-pipeline`: no stage reads `_a2kit_request_principal`. The
  authorize gate resolves dependencies via DI exclusively.

## Impact

- Affected code: `src/a2kit/packages/dispatch/stages.py`, possibly
  `src/a2kit/packages/auth/` and `src/a2kit/packages/mcp/` (the
  substrate-side writers). The audit cited
  `principal_middleware.py:43` as a contextvar setter.
- API: none for consumers; the externally-observable behaviour of
  `Principal` injection is unchanged.
- Tests: simplify — the dual-path tests collapse into one. Verify
  no stage reads the contextvar directly.
- Risk: low; the DI path is already documented as canonical per
  `principal-propagation` spec; this change brings code in line.
