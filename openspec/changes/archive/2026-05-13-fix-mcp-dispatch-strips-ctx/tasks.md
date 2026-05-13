# Tasks — fix-mcp-dispatch-strips-ctx

## 0. Prerequisites

- [x] 0.1 Baseline green: `make lint` + `make test` from current
      `main`. Record test count for parity-check at the end.
- [x] 0.2 Document the bug with a failing repro test that we
      expect to fail today and pass after the fix:
      `tests/test_transport_parity.py::test_tool_both_state_and_ctx_over_mcp`.
      Uses `fastmcp.Client(transport=build_mcp_server(app))` on a
      tool declaring both `state: State` and `ctx: ToolContext`.
      Assert returned payload structurally equals
      `{"msg": "x", "state_tag": "S", "has_ctx": True}`.
      Today this raises `TypeError: missing ... 'ctx'`. Document
      that the test is expected-fail until task 2 lands.

## 1. Exceptions — new diagnostic classes

- [x] 1.1 Add `A2KitContextBindingBroken(A2KitError, RuntimeError)`
      to `src/a2kit/exceptions.py`. Constructor:
      `(fn_name: str, *, ctx_param_name: str)`. Message:
      `f"a2kit-internal: rewritten MCP signature for {fn_name!r} "
      f"does not contain ctx parameter {ctx_param_name!r}. This "
      f"indicates a wrapper-chain regression; user code cannot "
      f"cause this. Please file an issue."`. Export from
      `a2kit.exceptions.__all__`.
- [x] 1.2 Add `A2KitInvalidContextAnnotation(A2KitError, TypeError)`
      to `src/a2kit/exceptions.py`. Constructor:
      `(fn_name: str, *, param_name: str, hint: str)`. Message
      includes both `fn_name` and `hint`. Export from
      `a2kit.exceptions.__all__`.
- [x] 1.3 Unit tests in `tests/test_exceptions.py`: both classes
      instantiate cleanly, expose expected attributes, render
      readable `str()`.

## 2. The fix — `_wrap_with_dispatch_hook` re-appends ctx

- [x] 2.1 Modify `_wrap_with_dispatch_hook(fn, hook, container)` in
      `src/a2kit/packages/mcp/server.py` to accept a new keyword
      argument `ctx_param_name: str | None = None`. Update the
      call site at `server.py:319` to pass
      `meta.context_param_name`.
- [x] 2.2 In the `new_params` construction (after the existing
      wire-params + `connection` block, before the
      `setattr(_wrapped, "__signature__", ...)` line), append fn's
      original ctx Parameter when `ctx_param_name` is set:
      `new_params.append(inspect.signature(fn).parameters[ctx_param_name].replace(kind=inspect.Parameter.KEYWORD_ONLY))`.
- [x] 2.3 After `__signature__` is set, assert the invariant: if
      `ctx_param_name` is set and not in
      `{p.name for p in new_params}`, raise
      `A2KitContextBindingBroken(fn.__qualname__, ctx_param_name=ctx_param_name)`.
- [x] 2.4 Verify task 0.2's expected-fail test now passes.
- [x] 2.5 Run the existing MCP test suite (`make test`); confirm
      no regressions on the existing
      `tests/test_field_logging_mcp_path.py` suite or any other
      MCP-touching test.

## 3. Reject `ctx: ToolContext | None` at decoration time

- [x] 3.1 Add `_is_optional_tool_context(ann)` helper in
      `src/a2kit/signature.py`. Returns `True` when `ann` is
      `ToolContext | None`, `Optional[ToolContext]`, or
      `Union[ToolContext, None]`. Reuses existing
      `_is_tool_context` for the member check.
- [x] 3.2 Modify `find_context_param(fn)` in
      `src/a2kit/signature.py` to detect the Optional form before
      the `_is_tool_context` check and raise
      `A2KitInvalidContextAnnotation(fn.__qualname__, param_name=name, hint=...)`
      with hint:
      `"ctx is always bound by the dispatcher when declared; "
      "drop '| None' from the annotation, or remove ctx entirely "
      "if the tool does not need it."`.
- [x] 3.3 Unit test in `tests/test_signature.py`:
      `find_context_param` raises on a function with
      `ctx: ToolContext | None`, raises on
      `Optional[ToolContext]`, accepts a plain `ctx: ToolContext`.
- [x] 3.4 Search `src/a2kit/` and `examples/` for any tool body
      using the Optional form; verify none exist (per design
      D-OPTIONAL-CTX search). Document the search in the task
      log; if any are found, migrate them as part of this task
      and document in the proposal's BREAKING note.

## 4. Transport-parity matrix

- [x] 4.1 Create `tests/test_transport_parity.py` with the
      4-tool fixture from design D-PARITY-MATRIX (one `Router`
      `R` with `tool_none`, `tool_state`, `tool_ctx`,
      `tool_both`, one `app.singleton(State, ...)`).
- [x] 4.2 Implement `_call_cli(app, tool_name, **kwargs)` helper
      using `cli.runtime.invoke_tool_sync`. Returns a normalized
      payload dict.
- [x] 4.3 Implement `_call_mcp(app, tool_name, **kwargs)` helper
      using `fastmcp.Client(transport=build_mcp_server(app))`.
      Returns a normalized payload dict (unwraps
      `result.structured_content` or `result.data` per FastMCP
      version).
- [x] 4.4 Implement `assert_parity(app, tool_name, kwargs, *, expected=None, expected_exc=None)`
      helper. On success: structural-equal payload both
      transports. On expected_exc: exact exception class match
      both transports.
- [x] 4.5 Case 1: `assert_parity(app, "tool_none", {"msg": "x"}, expected={"msg": "x"})`.
- [x] 4.6 Case 2: `assert_parity(app, "tool_state", {"msg": "x"}, expected={"msg": "x", "state_tag": "S"})`.
- [x] 4.7 Case 3: `assert_parity(app, "tool_ctx", {"msg": "x"}, expected={"msg": "x", "has_ctx": True})`.
- [x] 4.8 Case 4 (the v0.32 blocker):
      `assert_parity(app, "tool_both", {"msg": "x"}, expected={"msg": "x", "state_tag": "S", "has_ctx": True})`.
- [x] 4.9 Case 5: `assert_parity(app, "tool_none", {"msg": "x", "extra": "y"}, expected_exc=TypeError)`.
- [x] 4.10 Case 6: `assert_parity(app, "tool_state", {}, expected_exc=TypeError)`.
- [x] 4.11 Case 7: Add a fifth tool `tool_ctx_emits_event` that
      calls `await a2kit.ldd.event("tick", n=1)`. Assert event is
      delivered on both transports (ambient ctx populated on MCP
      side).
- [x] 4.12 Case 8: Add a sixth tool `tool_raises_value_error` that
      raises `ValueError("boom")`. Pre-envelope state: assert
      `ValueError` on CLI; assert wire `isError=True` on MCP
      (class-name introspection deferred to
      `mcp-structured-wire-error-envelope` change).
- [x] 4.13 Case 9: at module level, attempt to define a
      seventh tool with `ctx: a2kit.ToolContext | None = None`
      and assert it raises `A2KitInvalidContextAnnotation` at
      decoration time. Use a separate `def test_optional_ctx_rejected(): ...`
      wrapping the decoration in `pytest.raises`.

## 5. Stdio subprocess smoke (opt-in)

- [x] 5.1 Create `tests/test_transport_parity_stdio.py`. Skip
      unless `os.environ.get("A2KIT_SLOW_TESTS") == "1"`.
- [x] 5.2 One test: spawn `python -m a2kit_test_app demo serve`
      (or equivalent) via `mcp.client.stdio.stdio_client`,
      invoke `tool_both`, assert payload parity with case 4.
- [x] 5.3 Wire `A2KIT_SLOW_TESTS=1` into a separate CI job (or
      document the env var in `CONTRIBUTING.md` /
      `OPERATIONAL_CONTRACTS.md` for manual invocation). Default
      CI stays fast.

## 6. OPERATIONAL_CONTRACTS — new Q-Ctx section

- [x] 6.1 Add section "Q-Ctx: Context binding invariants" to
      `OPERATIONAL_CONTRACTS.md`. Document:
      - ctx is always bound when declared; never `None` at runtime
      - `ctx: ToolContext | None` is rejected at decoration time
      - the rewritten MCP signature MUST contain ctx when
        `meta.context_param_name` is set
      - the parity matrix at `tests/test_transport_parity.py`
        pins this contract; future wrapper-chain changes must
        not regress it
- [x] 6.2 Cross-link Q-Ctx → `tests/test_transport_parity.py`
      (file path) and the new diagnostic exception classes.

## 7. Spec delta

- [x] 7.1 Apply the `mcp-context-passthrough` spec delta from
      `openspec/changes/fix-mcp-dispatch-strips-ctx/specs/mcp-context-passthrough/spec.md`
      to `openspec/specs/mcp-context-passthrough/spec.md` during
      archival. (No change required during implementation; the
      delta file is the source of truth.)

## 8. Verify

- [x] 8.1 `make lint` green.
- [x] 8.2 `make test` green; test count is baseline + new cases
      from tasks 1.3, 3.3, 4.5-4.13, 5.x. Record the delta.
- [x] 8.3 Manual smoke against a2web v0.6.0: build a fresh wheel
      from this branch, install in a2web's editable env, run a
      Claude Code MCP session against `mcp__a2web__fetch`,
      confirm tool calls succeed end-to-end.
- [x] 8.4 Confirm the v0.32 outage is closed: re-run the bug
      reporter's reproducer
      (`A2KIT_FEEDBACK_v0.32-mcp.md` §Blocker, "Any tool that
      declares both ... AND ctx") against the in-memory
      FastMCP client; expect successful response, not the bare
      error string.
