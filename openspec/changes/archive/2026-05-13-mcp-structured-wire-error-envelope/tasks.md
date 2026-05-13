# Tasks — mcp-structured-wire-error-envelope

## 0. Prerequisites

- [x] 0.1 Baseline green: `make lint` + `make test`.
- [x] 0.2 Document the bug with a failing repro test:
      `tests/test_wire_error_envelope.py::test_value_error_returns_structured_payload`.
      Build an app with a tool that raises `ValueError("boom")`;
      invoke via `fastmcp.Client(transport=build_mcp_server(app))`;
      assert response is `isError=True` and
      `json.loads(content[0].text) == {"class": "ValueError", "message": "boom"}`.
      Today this fails (bare `"Error calling tool 'X'"`).

## 1. The wrapper

- [x] 1.1 Add `_wrap_with_error_envelope(fn, *, debug: bool)` to
      `src/a2kit/packages/mcp/server.py`. Catches `Exception`
      (not `BaseException`), excludes `FastMCPError` via
      `except FastMCPError: raise`, handles
      `BaseExceptionGroup` per design D-EXCLUSION-LIST.
- [x] 1.2 Add `_build_payload(exc, *, debug) -> dict[str, Any]`
      helper per design D-PAYLOAD-SHAPE. Two required keys,
      optional `traceback`.
- [x] 1.3 Import `FastMCPError`, `ToolError` from
      `fastmcp.exceptions` at module top of `server.py`.
- [x] 1.4 Delete `_wrap_with_debug_traceback` (lines ~124-148)
      and its caller. The new wrapper subsumes its purpose.
- [x] 1.5 Update wrapper-chain assembly (~line 269-330) to
      install `_wrap_with_error_envelope` as the outermost
      wrapper, unconditional (not gated on `app_debug`); pass
      `debug=app_debug`.

## 2. Test cases

- [x] 2.1 Make task 0.2's repro test pass.
- [x] 2.2 `test_value_error_with_debug_includes_traceback`:
      same setup, `App(debug=True)`, assert
      `json.loads(...).keys() >= {"class", "message", "traceback"}`
      and traceback contains `"ValueError: boom"` line.
- [x] 2.3 `test_author_raised_tool_error_passes_through`: tool
      raises `ToolError("custom message")`. Assert wire response
      `isError=True` and `content[0].text == "custom message"`
      (NOT JSON-wrapped).
- [x] 2.4 `test_cancellation_propagates_unwrapped`: tool body
      `raise asyncio.CancelledError`; client invocation surfaces
      cancellation (e.g. `asyncio.CancelledError` on the client
      side, NOT a `ToolError`-wrapped response). Use
      `fastmcp.Client` cancellation semantics or
      `pytest.raises(asyncio.CancelledError)` on the awaited
      `call_tool`.
- [x] 2.5 `test_type_error_class_preserved`: tool calls
      `int("not a number")`, asserting wire payload has
      `"class": "ValueError"` (matching the actual exception).
- [x] 2.6 `test_message_with_special_chars_round_trips`: tool
      raises `ValueError("a\nb\"c")`; assert
      `json.loads(content[0].text)["message"] == "a\nb\"c"`.

## 3. Spec delta

- [x] 3.1 Apply the `operational-contracts` delta from
      `openspec/changes/mcp-structured-wire-error-envelope/specs/operational-contracts/spec.md`
      during archival.

## 4. OPERATIONAL_CONTRACTS — update Q5

- [x] 4.1 Update Q5 (or equivalent error-envelope section) in
      `OPERATIONAL_CONTRACTS.md`. New paragraph:
      *"a2kit guarantees that any uncaught exception raised by
      a tool body or its wrapper chain reaches the MCP wire as
      `isError: true` with a JSON-encoded text payload of shape
      `{"class": "<ExceptionClassName>", "message": "<str(exc)>"}`.
      When `App(debug=True)`, the payload additionally includes
      `"traceback": "<rendered traceback>"`. The contract is
      enforced by a2kit's outermost tool wrapper and does NOT
      depend on FastMCP's `mask_error_details` flag, which a2kit
      treats as an internal implementation detail. `asyncio.CancelledError`,
      `KeyboardInterrupt`, `SystemExit`, and
      `fastmcp.exceptions.FastMCPError` (including
      author-raised `ToolError`) propagate unwrapped. CLI
      transport is unchanged — exceptions surface as
      `error: <message>` on stderr (with traceback under
      `debug=True`) and non-zero exit; the structured envelope is
      an MCP-transport guarantee only."*
- [x] 4.2 Cross-link Q5 → `tests/test_wire_error_envelope.py`.

## 5. Verify

- [x] 5.1 `make lint` green.
- [x] 5.2 `make test` green; record test count delta.
- [x] 5.3 Cross-check: invoke the `fix-mcp-dispatch-strips-ctx`
      blocker's original reproducer with the envelope shipping
      (but the dispatch fix NOT yet shipped — hypothetically).
      Confirm the wire payload now reads
      `{"class": "TypeError", "message": "<fn>() missing 1
      required keyword-only argument: 'ctx'"}` instead of the
      bare error string. (Then unstrip the dispatch fix; both
      ship.)
