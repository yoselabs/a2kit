## 1. Audit current contextvar reads

- [x] 1.1 Grep `src/a2kit/` for `_a2kit_request_principal` and list every read and write site
- [x] 1.2 Confirm the audit-cited locations: `stages.py:173-175`, `stages.py:196-204`, `packages/auth/principal_middleware.py:43`, the ContextVar declaration site
- [x] 1.3 Identify any non-stage reader outside the substrate adapter

## 2. Remove stage-level contextvar reads

- [x] 2.1 Extract the read in `DispatchHookStage.wrap()` into `dispatch/_principal_scope.py:seed_principal_into_wire`; stage calls the helper
- [x] 2.2 Replace the contextvar fallback in `_run_authorize_gate` with helper-based seeding; gate resolves `Principal` from the DI scope only
- [x] 2.3 Comment in `stages.py`: Principal resolution is DI-only and the seeding helper is the substrate handoff seam

## 3. Substrate-side Principal writers

- [x] 3.1 Substrate adapters (`packages/auth/`, `packages/mcp/`, `packages/http/`) continue to publish Principal at their authentication boundary
- [x] 3.2 FastAPI Security guard adapter unchanged — `_lift_principal_into_scope` keeps seeding wire_kwargs and the contextvar
- [x] 3.3 Contextvar `set(...)` retained as substrate-internal handoff; full removal deferred (see design Decision 1, revised 2026-05-26)

## 4. Contextvar fate

- [x] 4.1 ContextVar declaration retained — single read site is now `dispatch/_principal_scope.py`; stages source is grep-clean
- [x] 4.2 Stage-source grep gate confirms no `stages.py` reference

## 5. Tests

- [x] 5.1 `tests/test_principal_single_source.py::test_di_principal_provider_flows_to_tool_body` — DI provider override flows to body
- [x] 5.2 `tests/test_principal_single_source.py::test_no_provider_and_no_substrate_write_raises_clear_error` — clear `RuntimeError` on no Principal
- [x] 5.3 `tests/test_principal_single_source.py::test_dispatch_stages_source_has_no_principal_contextvar_read` — grep gate
- [x] 5.4 Helper unit tests at `tests/packages/dispatch/test__principal_scope.py`
- [x] 5.5 Existing `principal-propagation` tests still pass on both MCP and HTTP

## 6. Documentation + lint

- [x] 6.1 CHANGELOG entry under `Unreleased`
- [x] 6.2 Rule documented at the read site (`_principal_scope.py` docstring); ANTIPATTERNS.md entry deferred — grep gate enforces
- [x] 6.3 `make lint` clean
- [x] 6.4 `openspec validate --changes --strict` passes
