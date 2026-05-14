# Tasks — cross-transport parity for unknown-kwarg rejection

## 0. Prerequisites

- [x] 0.1 Baseline: `make test` green (864 pass + case 5 skipped).
- [x] 0.2 Confirm `tests/test_transport_parity.py:177-188`
      `test_case5_unknown_kwarg_parity` is the skip target. Read its
      assertion shape — it expects both legs to raise.

## 1. Probe — does the gap still exist?

- [x] 1.1 Locally remove the `@pytest.mark.skip(...)` decorator at
      `tests/test_transport_parity.py:177`.
- [x] 1.2 `uv run pytest tests/test_transport_parity.py
      -k test_case5 -v` and observe:
      - **Pass**: skip rationale is obsolete after rebuild; skip is
        dead weight. Skip to task 3.
      - **Fail**: real gap exists. Continue to task 2.

## 2. Fix the runtime dispatcher (only if 1.2 fails)

- [x] 2.1 Identify the silent-drop site. Likely candidates:
      - `src/a2kit/packages/cli/runtime.py::_invoke_tool_in_process`
        before `fn(**call_kwargs)` (line ~63)
      - `src/a2kit/packages/cli/builder.py` callback body where
        `call_kwargs` is assembled from typer kwargs
      - `src/a2kit/packages/testing/client.py::TestClient.invoke` if
        it constructs the kwargs dict before passing to fastmcp
- [x] 2.2 Add a validation step: after `call_kwargs` is built but
      before `fn(**call_kwargs)`, compute
      `declared = set(inspect.signature(fn).parameters)` and
      `unknown = set(call_kwargs) - declared`. If `unknown` is
      non-empty, raise `TypeError(f"unexpected keyword arguments: {sorted(unknown)}")`.
- [x] 2.3 Add a regression test for the runtime dispatcher path
      specifically — bypass the TestClient and call
      `_invoke_tool_in_process` directly with an unknown kwarg.

## 3. Spec delta — mcp-context-passthrough

- [x] 3.1 Author `openspec/changes/cross-transport-parity-strict/
      specs/mcp-context-passthrough/spec.md`:
      - ADDED Requirement: "Unknown kwargs are rejected at both
        transport boundaries"
      - Scenario: programmatic CLI call with undeclared kwarg
        raises `TypeError`; FastMCP call with same shape raises
        `ToolError` carrying a `TypeError`-class envelope

## 4. OPERATIONAL_CONTRACTS

- [x] 4.1 Add `Q-Kwargs: Unknown-kwarg posture` (or similar
      section). Document:
      - Both transports reject unknown kwargs
      - CLI Typer surfaces as `BadParameter` (`--unknown-flag`)
      - FastMCP surfaces as `ToolError(json)` wrapping `TypeError`
      - The runtime dispatcher itself raises `TypeError` directly
        (visible to any programmatic caller bypassing the typer
        layer)

## 5. Verify

- [x] 5.1 `tests/test_transport_parity.py::test_case5_unknown_kwarg_parity`
      runs (not skipped) and passes.
- [x] 5.2 `make test` green; case 5 contributes one new asserting
      test rather than one skip.
- [x] 5.3 `make lint` green.
- [x] 5.4 If task 2 fired: regression test from 2.3 passes.

## 6. Out-of-scope

- [x] 6.1 Strict positional-arg vs keyword-arg parity. The current
      contract is keyword-only via the Typer / FastMCP layer; positional
      args are not exposed.
- [x] 6.2 Type-coercion of valid kwargs. Pydantic-driven coercion
      happens in FastMCP; CLI coerces via Typer / pydantic — those
      are already parity-tested upstream.
