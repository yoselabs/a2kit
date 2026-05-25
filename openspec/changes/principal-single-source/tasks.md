## 1. Survey the dual paths

- [ ] 1.1 Grep `src/a2kit/` for `_a2kit_request_principal` and list every read and write site
- [ ] 1.2 Confirm the audit-cited locations: `stages.py:173-175`, `stages.py:196-204`, `packages/auth/principal_middleware.py:43`, the ContextVar declaration site (likely `packages/context/principal.py`)
- [ ] 1.3 Identify any non-stage reader outside the substrate adapter; plan per-site migration

## 2. Remove stage-level contextvar reads

- [ ] 2.1 In `src/a2kit/packages/dispatch/stages.py`, delete the contextvar read and the kwargs re-seed at `DispatchHookStage.wrap()` (lines 173-175 per audit)
- [ ] 2.2 Delete the contextvar fallback in `_run_authorize_gate` (lines 196-204); resolve `Principal` from the DI scope only
- [ ] 2.3 Add a brief comment in `stages.py` documenting that Principal resolution is DI-only and a contextvar read is a defect

## 3. Substrate adapter writes Principal to DI scope

- [ ] 3.1 In `packages/auth/principal_middleware.py`, ensure the middleware writes Principal into the per-call DI scope (likely already present)
- [ ] 3.2 In the FastAPI Security adapter, ensure the resolved Principal is written into the per-request DI scope before tool body dispatch (likely already present)
- [ ] 3.3 Remove any contextvar `set(...)` calls in substrate adapters

## 4. Delete the contextvar

- [ ] 4.1 Delete the `_a2kit_request_principal` ContextVar declaration at its source site
- [ ] 4.2 Confirm via grep that no module references the deleted symbol; lint will catch any straggler

## 5. Tests

- [ ] 5.1 Add scenario: DI provider override for Principal flows through to tool body (principal-propagation spec scenario 1)
- [ ] 5.2 Add negative scenario: no provider, no substrate write → clear "no provider for Principal" error (scenario 2)
- [ ] 5.3 Add scenario: DispatchHookStage source contains no contextvar read (dispatch-pipeline spec scenario 1) — grep-based assertion in a test
- [ ] 5.4 Add scenario: AuthorizeGateStage source contains no contextvar fallback (scenario 2) — same grep approach
- [ ] 5.5 Verify existing `principal-propagation` tests pass unchanged on both MCP and HTTP

## 6. Documentation + validation

- [ ] 6.1 Update CHANGELOG `Unreleased` with the removal of the contextvar (private API) and the migration recipe
- [ ] 6.2 Add an `ANTIPATTERNS.md` entry: "Reading `Principal` from a contextvar"
- [ ] 6.3 `make lint` clean
- [ ] 6.4 `openspec validate --changes --strict` passes for `principal-single-source`
