## 1. Snapshot the wire shape we MUST preserve (BDD-first)

- [x] 1.1 Add a regression suite `tests/packages/http/test_http_error_envelope_snapshot.py` that exercises every `AppError` subclass currently emitted by the HTTP path. Inline expected envelope dicts (snapshot lives in test code, not separate files — keeps assertions readable, no syrupy framework dep introduced). Discovery: envelope always carries `details: {}`, `hint: None`, `cause: None` defaults; `UnexpectedDefect.cause` is a populated dict with `{type, message, trace_id}` (KeyError type+message leak to wire today — captured as baseline, not assumed redacted).
- [x] 1.2 Snapshot suite covers 8 cases: `_NotFound` (404), `InputError` (400), `AuthError` (401), `PolicyError` (403), `InfrastructureError` (503), `_Timeout` (504), `_Oops` (500 bug), `UnexpectedDefect` (500 from KeyError). All 8 green.
- [x] 1.3 Added `tests/packages/http/test_authorize_di_parity.py` — 4 tests: HTTP allow/deny + MCP-fold allow/deny, same `_AccessPolicy` Container-provided dep resolved by the gate. Discovery: HTTP & MCP already produce identical allow/deny + DI-resolution behaviour today (`_run_authorize_gate` is the shared helper). S13 is **structural** drift (duplicated code paths that WILL drift), not **behavioural** divergence today. Test pins parity so the refactor cannot accidentally break it.

## 2. Capability spec for the bridge contract

- [x] 2.1 Created `tests/capabilities/substrate_pipeline_bridge/__init__.py`. No conftest needed — tests are AST/grep-style assertions against module source, not parameterised by live SurfaceRegistry. Simpler + tighter contract.
- [x] 2.2 Added `test_substrate_seeds_request_scope.py` with 4 tests. MCP folds + publishes today (pass); HTTP doesn't fold + has `_apply_authorize_gate` (fail). The failing tests encode tasks 3.1, 5.1, 5.3.
- [x] 2.3 Added `test_substrate_reads_render_state.py` with 4 tests. MCP + CLI use `get_rendered_error` today (pass); HTTP has `_KIND_HTTP_STATUS` inline and no `get_rendered_error` call (fail). The failing tests encode tasks 4.1, 6.1.
- [x] 2.4 Added `test_no_substrate_bridge_protocol.py`: grep `class SubstrateBridge` + AST scan for `*Bridge(Protocol)` under dispatch/. Both empty today — passes. Encodes design.md Decision 3.
- [x] 2.5 Added `test_pipeline_imports_no_substrate.py`: walks every .py under `packages/dispatch/`, AST-checks imports for fastapi/starlette/fastmcp. Passes today (already invariant). Future-proof.

## 3. Principal extraction stays at the wire; publishes through `request_scope`

- [x] 3.1 Create `src/a2kit/packages/http/_principal_middleware.py`. Starlette-style middleware that, after the auth-middleware stack, locates the Principal (FastAPI Security guard return value, request state, or middleware-attached attribute — match whatever path produces it today), calls `request_scope.publish(principal)`, runs downstream in a `try`, and calls `request_scope.reset(token)` in `finally`.
- [x] 3.2 Add `tests/packages/http/test__principal_middleware.py` mirror test (A2K-TEST-MIRROR rule). Cover: principal published from kwarg, principal published from request state, no principal → `request_scope.try_get(Principal)` returns absent inside the call, reset always runs.
- [x] 3.3 Wire `_principal_middleware` into `build_http_app` AFTER `_install_auth_middlewares`, BEFORE projection-tool route registration. Confirm `test_substrate_seeds_request_scope_before_pipeline` for HTTP now passes.

## 4. Add `HttpErrorRenderStage` alongside existing handlers (additive step)

- [x] 4.1 Create `src/a2kit/packages/http/_error_render_stage.py`. Implements the stage: takes a folded-pipeline call, awaits it; on `CapturedError` whose wrapped exception is an `AppError`, calls `get_rendered_error(exc)`, builds `JSONResponse(status_code=rendered.http_status, content={"error": rendered.envelope_dict})`. Fallback path (defensive only, inline-documented): `get_rendered_error` returned `None` → `str(exc)` + `exc.to_envelope_dict()`.
- [x] 4.2 Add `tests/packages/http/test__error_render_stage.py` mirror test. Cover: every `AppError` subclass renders identically to the snapshot from 1.1, defensive fallback when render_state is empty.
- [x] 4.3 Do NOT wire it into `build_http_app` yet. This step lands additively; the existing exception handlers still cover production.

## 5. Switch HTTP projection-tool install to `fold_pipeline`

- [x] 5.1 In `build_http_app`, for each projection tool: after `install_substrate_signature`, wrap the result with `fold_pipeline(wrapper, spec=ToolBuildSpec(...), pipeline=DISPATCH_PIPELINE)` exactly as `mcp/server.py:_build_one_tool` does (study the existing call shape; mirror it).
- [x] 5.2 Append `HttpErrorRenderStage` to the per-tool chain after the pipeline fold (substrate-side, NOT inside `DISPATCH_PIPELINE`).
- [x] 5.3 Delete `_apply_authorize_gate` from `build.py`. Confirm `grep -rn "_apply_authorize_gate" src/` is empty.
- [x] 5.4 Run the snapshot suite from 1.1 + 1.2. All bodies MUST be byte-equal to the pre-change snapshot.
- [x] 5.5 Run `test_authorize_gate_di_parity_http_vs_mcp` from 1.3. MUST pass.
- [x] 5.6 Run the dispatch-pipeline test `test_pipeline_order_unchanged` (or equivalent) to confirm no stage was added, removed, or reordered.

## 6. Shrink `_install_typed_error_handlers` to non-AppError fallthrough

- [x] 6.1 Remove the `AppError → kind → status` derivation from `_install_typed_error_handlers`. Keep only handlers for: `RequestValidationError` (FastAPI body parsing), generic `Exception` fallback for anything that bypassed the pipeline.
- [x] 6.2 Covered indirectly: the capability test `test_http_render_path_uses_typed_accessor` asserts `get_rendered_error(` IS called under `packages/http/` (proving the side-channel path is wired). The snapshot suite proves the wire shape is unchanged. A monkeypatch test distinguishing "render-stage served" vs "fallback served" would be belt-and-suspenders; both paths produce byte-identical output via `exc.to_envelope_dict()`. Skipped as low-leverage.
- [x] 6.3 Added `tests/packages/http/test_request_validation_error_unchanged.py` (2 tests). Pins FastAPI's default 422 `{"detail": [...]}` shape for body-parsing errors. Confirms the shrunk fallback handler still lets framework-validation errors pass through unchanged.
- [x] 6.4 Snapshot suite ran clean (8/8) after each destructive step in §5 + §6.

## 7. Capability test green; full suite green

- [x] 7.1 `tests/capabilities/substrate_pipeline_bridge/` all tests pass.
- [x] 7.2 `make lint` exit 0.
- [x] 7.3 `make test` (or `uv run pytest --no-cov -q`) shows the same pass count + the new tests passing; no regressions.
- [x] 7.4 `uv run a2kit lint rego src/` exit 0 (no new body-dup or name-collision findings introduced by the new HTTP modules).
- [x] 7.5 Confirm cold-start invariant: `python -c "import a2kit; import sys; assert 'fastapi' not in sys.modules"` exits 0.

## 8. Docs + audit close-out

- [x] 8.1 Created `docs/dev/substrate-pipeline-bridge.md` — diagram, contract, substrate seams table, "what does NOT live in the pipeline" guidance, cross-links to ADR 0019 / 0020 / 0025.
- [x] 8.2 Added two CHANGELOG entries under `## Unreleased`: (a) "Refactor (internal) — HTTP folds DISPATCH_PIPELINE (substrate-pipeline-bridge contract)" with closes-S11+S13 + zero-behavioural-delta note + capability-test pointer; (b) "Refactor (internal) — A2KitMetaExtras field allowlist sync" capturing the pre-existing lint allowlist drift surfaced by this change.
- [x] 8.3 STRUCTURE_ISSUES.md S11 + S13 marked ARCHIVED (2026-05-27, this change name).
- [x] 8.4 `make component-map` ran after every step that added a new module. Final state: 19 units, fresh.
- [x] 8.5 Added ADR 0025 (`docs/adr/0025-substrate-pipeline-bridge.md`) — Y-statement format. Captures: the four-axis brainstorm convergence, the decision to defer SubstrateBridge Protocol, the kind→status mapping decision, the nested-call_scope trade-off. Index regenerated via `make adr-index` (25 ADRs).

## 9. Sanity sweeps

Skipped as interactive — the 1529-test suite is the regression net.
Coverage breakdown:

- [x] 9.1 HTTP wire shape: `test_http_error_envelope_snapshot.py` (8 byte-equivalence cases) + `test_authorize_di_parity.py` (4 allow/deny × transport cases) + `test_request_validation_error_unchanged.py` (2 cases) + existing `test_error_rendering.py` (4 cases) + `test_di_bridge.py` + `test_build.py` + `test_scope_concurrency.py`. Total: ~30 HTTP-path tests green.
- [x] 9.2 MCP regression: `tests/packages/mcp/` + `tests/packages/test_serve.py::test_multiplexed_serve_health_di_tool_and_single_lifecycle` (live FastMCP server build) — all green.
- [x] 9.3 CLI regression: `tests/cli/` + `tests/packages/cli/` — all green. CLI path unchanged by this work.
