## 0. Prerequisites

- [x] 0.1 Baseline green before this change.
- [x] 0.2 Confirmed `_wrap_with_ldd_state` and `_invoke_tool_in_process` already enter `ldd_state_for_call` unconditionally.
- [x] 0.3 Grepped for `MODE_MISSING_CTX_PARAM` / `missing_ctx_param` references: `exceptions.py` (constant), `mcp/server.py:76,463` (docstrings), `ldd/__init__.py:163` (raise), `test_ambient_ldd_ctx.py:128,159` (tests).

## 1. Failing tests first (BDD)

- [x] 1.1 Created `tests/test_ldd_emission_without_ctx_param.py` with 4 BDD scenarios:
  - MCP dispatch of a no-ctx tool emitting `a2kit.ldd.event(...)` captures the event on the test client.
  - MCP dispatch does not raise `AmbientContextMissing`.
  - CLI runtime emits LDD lines to stderr for no-ctx tools.
  - Tools that DO declare ctx still receive it as a kwarg (regression).
- [x] 1.2 Updated `tests/test_ambient_ldd_ctx.py::test_ambient_dispatch_succeeds_without_ctx_param` — flipped from "expect Mode B raise" to "expect success + captured event."
- [x] 1.3 Kept `test_ambient_context_missing_mode_missing_ctx_param_message` — it tests manual `ldd_state_for_call(ctx=None)` misuse, which still legitimately raises Mode B.
- [x] 1.4 All new/updated tests initially failed with Mode B raise as expected.

## 2. MCP wrapper — unconditional ctx synthesis

- [x] 2.1 `_ensure_ctx_in_rewritten_signature` extended: when `ctx_param_name` is None, synthesize a `_a2kit_ctx` Parameter annotated `fastmcp.Context` (resolved class).
- [x] 2.2 `_wrap_with_dispatch_hook` early-exit condition tightened: skip wrap only when `not _has_injectables and ctx_param_name is not None` (ctx already in fn's signature). Otherwise wrap so the synthesis path runs.
- [x] 2.3 Wrapper pops `_a2kit_ctx` from kwargs before calling dispatch hook + tool body so the body never sees the framework-internal name.
- [x] 2.4 `_wrap_with_ldd_state` extracts ctx from the synthesized name when `ctx_param_name` is None, pops before invoking the body.
- [x] 2.5 `SYNTHESIZED_CTX_PARAM_NAME = "_a2kit_ctx"` constant exported alongside the helpers.

## 3. CLI runtime — unconditional ctx synthesis

- [x] 3.1 `_invoke_tool_in_process`'s `_run_inside_call` synthesizes `StderrToolContext()` for ambient binding even when `ctx_param_name` is None.
- [x] 3.2 The synthesized ctx is NOT injected into `call_kwargs` when the tool didn't declare ctx — only fed to `ldd_state_for_call`.

## 4. LDD primitives — Mode B retired (from framework paths)

- [x] 4.1 Decision changed during implementation: `_require_ambient_state` kept as-is. The `state.ctx is None` branch still raises Mode B — but the framework's wrapper guarantees non-None ctx, so the raise is unreachable from a real dispatch. Manual `ldd_state_for_call(ctx=None)` misuse still trips it (documented behavior).
- [x] 4.2 `MODE_MISSING_CTX_PARAM` constant preserved.

## 5. Pre-existing bug fixed (surfaced by 2.2)

- [x] 5.1 `_wrap_with_dispatch_hook` was previously losing `fn`'s return annotation when rewriting `__signature__`. The early-exit for no-injectable tools hid this. Extracted `_install_rewritten_signature` helper that sets `__signature__.return_annotation` AND `__annotations__["return"]`.
- [x] 5.2 Verified 4 regression failures fixed: `test_invoke_returns_value`, `test_listview_e2e_passthrough_when_no_list_view_settings`, `test_testclient_invoke_returns_tool_value`, `test_call_wire_tsv_for_list_of_models`.

## 6. Spec delta

- [x] 6.1 `MODIFIED` `AmbientContextMissing distinguishes...` in `operational-contracts`.
- [x] 6.2 `MODIFIED` `LDD primitives require an active tool dispatch` in `operational-contracts`.
- [x] 6.3 `ADDED` `Ambient ctx is non-None inside any framework dispatch` in `mcp-context-passthrough`.

## 7. Documentation

- [x] 7.1 `CHANGELOG.md` Unreleased "Changed" subsection covers the shift + LDD philosophy alignment + companion return-annotation fix.
- [x] 7.2 `OPERATIONAL_CONTRACTS.md` Q8 rewritten with the new uniform contract.
- [x] 7.3 `docs/feedback-responses/v0.38-a2web-round-10.md` Friction B updated to "Shipped" + summary table row updated. Marker proposal noted as scrapped.

## 8. Validate + archive

- [x] 8.1 `openspec validate relax-ldd-ambient-requirement --strict` passes.
- [x] 8.2 Full gate green: make lint, ty check src/, 926 pytest passing (922 baseline + 4 net new).
- [ ] 8.3 Archive via `openspec archive relax-ldd-ambient-requirement -y`.

## 9. Sanity / non-tasks

- [x] 9.1 No new public surface symbols.
- [x] 9.2 No `Router.emits_ldd` marker.
- [x] 9.3 No `context-as-protocol` work — that's a separate proposal queued next.
- [x] 9.4 Did NOT remove `MODE_MISSING_CTX_PARAM` constant; kept as historical.
- [x] 9.5 Cold-start budget unchanged.
