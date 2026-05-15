## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov`.
- [ ] 0.2 Confirm by reading: `_wrap_with_ldd_state` at `packages/mcp/server.py:55-99` and `_invoke_tool_in_process` at `packages/cli/runtime.py:61-82` already enter `ldd_state_for_call` unconditionally. (Spike confirmed during round-10 design.)
- [ ] 0.3 Grep current test suite for assertions about Mode B / `MODE_MISSING_CTX_PARAM` so we know what to update: `grep -rn "MODE_MISSING_CTX_PARAM\|missing_ctx_param" tests/ src/`.

## 1. Failing tests first (BDD per `feedback_bdd_first`)

- [ ] 1.1 Create `tests/packages/mcp/test_ldd_emission_without_ctx_param.py`:
  - Tool on a Router with NO `ctx` param in signature; body calls `await a2kit.ldd.event("evt", k=1)`.
  - Drive through real `fastmcp.Client(transport=...)` via `a2kit.testing.client`.
  - Assert: invocation completes without raising; `client.events` captures the event with correct name + payload + `elapsed_ms`.
- [ ] 1.2 Create `tests/packages/cli/test_ldd_emission_without_ctx_param.py`:
  - Same tool shape, invoked via the CLI runtime (`_invoke_tool_in_process` directly, or via the CliRunner).
  - Assert: invocation completes; LDD lines render to captured stderr in the expected format.
- [ ] 1.3 Add a regression assertion to `tests/test_ambient_context_missing.py` (or wherever Mode B is currently asserted): a tool with no ctx + body emitting LDD, dispatched normally, must NOT raise. Conversely, calling `a2kit.ldd.event(...)` at module-level (no dispatch) still raises Mode A.
- [ ] 1.4 Update or delete any test that asserts Mode B raises *inside a dispatch*. Identify via the grep from 0.3.
- [ ] 1.5 Confirm new tests in 1.1 / 1.2 fail today (expected: `AmbientContextMissing` Mode B).

## 2. MCP wrapper — unconditional ctx synthesis

- [ ] 2.1 Update `_ensure_ctx_in_rewritten_signature` (`packages/mcp/server.py:329`):
  - When `ctx_param_name` is None, synthesize a Parameter named `_a2kit_ctx` annotated `fastmcp.Context` (resolved class, not string), kind KEYWORD_ONLY.
  - Append to `new_params` so fastmcp introspects and injects ctx.
- [ ] 2.2 Update `_wrap_with_dispatch_hook` (`packages/mcp/server.py:234`):
  - When `ctx_param_name` is None, extract ctx from kwargs under the synthesized name (`_a2kit_ctx`) and pass into ambient binding.
  - Do NOT inject into `merged` for the tool body — the tool's original signature doesn't declare it.
- [ ] 2.3 Update `_wrap_with_ldd_state` (`packages/mcp/server.py:55`):
  - When `ctx_param_name` is None, read ctx from `_a2kit_ctx` in kwargs.
  - Pop `_a2kit_ctx` from kwargs before invoking the wrapped fn so the tool body never sees the synthesized name.
- [ ] 2.4 Verify the synthesized Parameter doesn't collide with consumer-defined params (`_a2kit_*` prefix should be reserved; check `grep -rn "_a2kit_" src/a2kit/`).

## 3. CLI runtime — unconditional ctx synthesis

- [ ] 3.1 Update `_invoke_tool_in_process` (`packages/cli/runtime.py:61-82`):
  - Always synthesize `ctx_for_ldd = StderrToolContext()` for ambient binding.
  - Inject `call_kwargs[ctx_param_name] = ctx_for_ldd` ONLY when `ctx_param_name` is set (today's behaviour, preserved).
- [ ] 3.2 Confirm CLI subcommands routing through `Container.dispatch` correctly receive the synthesized ctx in ambient state.

## 4. LDD primitives — retire Mode B raise

- [ ] 4.1 Update `_require_ambient_state` in `packages/ldd/__init__.py:152-163`:
  - Keep the `state is None` branch (Mode A — fires outside dispatch).
  - Remove (or make unreachable) the `state.ctx is None` branch.
  - Add an internal assertion / type guard so type-checker knows ctx is non-None after the function returns.
- [ ] 4.2 Mark `AmbientContextMissing.MODE_MISSING_CTX_PARAM` as historical in its docstring (don't remove the constant — external callers may reference it).
- [ ] 4.3 Run new tests 1.1 / 1.2; they pass. Run existing test suite; identify any regressions and update tests as needed.

## 5. Spec delta

- [ ] 5.1 `MODIFIED` requirement in `mcp-context-passthrough`: "ambient ctx is non-None inside any framework dispatch" (was: conditional on signature declaration).
- [ ] 5.2 `MODIFIED` requirement in `operational-contracts` Q8 wording — sink-side emission decoupled from ctx availability.
- [ ] 5.3 `ADDED` scenarios for the new uniform behaviour.

## 6. Documentation

- [ ] 6.1 `CHANGELOG.md` Unreleased entry under "Changed" or "Fixed" — describe the behavior shift, why it aligns with LDD's log-driven philosophy.
- [ ] 6.2 `OPERATIONAL_CONTRACTS.md` Q8: rewrite the "ambient ctx requires both dispatch + ctx-in-signature" framing into "ambient ctx is non-None inside any dispatch; LDD primitives need only dispatch."
- [ ] 6.3 Update `docs/feedback-responses/v0.38-a2web-round-10.md` Friction B to "Shipped as relax-ldd-ambient-requirement" (replaces the marker counter-proposal).

## 7. Validate + archive

- [ ] 7.1 `openspec validate relax-ldd-ambient-requirement --strict` passes.
- [ ] 7.2 Full gate green.
- [ ] 7.3 Archive: `openspec archive relax-ldd-ambient-requirement -y`.

## 8. Sanity / non-tasks

- [ ] 8.1 No new public surface symbols.
- [ ] 8.2 No `Router.emits_ldd` marker.
- [ ] 8.3 No `context-as-protocol` work — that's a separate proposal.
- [ ] 8.4 Do NOT remove `MODE_MISSING_CTX_PARAM` constant; mark historical.
- [ ] 8.5 Cold-start budget unchanged (no new eager imports).
