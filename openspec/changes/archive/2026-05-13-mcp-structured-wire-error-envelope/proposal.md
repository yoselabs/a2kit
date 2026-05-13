# a2kit owns the MCP wire-error envelope (independent of FastMCP)

## Why

When a tool body or wrapper raises uncaught under MCP, the wire
returns:

```json
{"content":[{"type":"text","text":"Error calling tool 'ping'"}],"isError":true}
```

No exception class, no message, no traceback. Even with
`App(debug=True)` — which sets `mask_error_details=False` per
`packages/mcp/server.py:294` — the wire envelope collapses to the
bare string under the pinned FastMCP version.

The `operational-contracts` spec already requires structured
errors on the MCP wire (Requirement: *Error envelope for
unhandled tool exceptions* — JsonRpcError with `code=-32603`,
message includes `str(exc)`, traceback under `debug=True`). The
implementation does not honor this requirement because the
guarantee was outsourced to FastMCP's `mask_error_details`
semantics, which have shifted across FastMCP minor versions
(round 6 of consumer feedback already burned on this).

a2kit needs to **own the wire bytes**, not delegate to a
third-party flag that has demonstrated drift.

### The FastMCP escape hatch

FastMCP's tool-dispatch path re-raises `FastMCPError` subclasses
(including `ToolError`) **unchanged** — before the
`mask_error_details` branch runs. So a wrapper that catches
`Exception` and re-raises `ToolError(json.dumps(payload))` puts
arbitrary text on the wire verbatim, regardless of FastMCP's
masking behavior.

## What Changes

- New outermost wrapper `_wrap_with_error_envelope(fn, *, debug)`
  in `packages/mcp/server.py`. Catches `Exception` (deliberately
  not `BaseException`); excludes `FastMCPError` and subclasses
  via an explicit `except FastMCPError: raise` guard so
  author-raised `ToolError("msg")` passes through unwrapped.
- The wrapper builds payload
  `{"class": type(exc).__name__, "message": str(exc)}`; when
  `debug=True` adds `"traceback": traceback.format_exc()`.
- Re-raises `ToolError(json.dumps(payload)) from exc`. FastMCP
  serializes the message verbatim into
  `content[0].text` with `isError: true`.
- **Replaces** `_wrap_with_debug_traceback` (current outermost
  when `app_debug`). That wrapper's "embed traceback in
  `str(exc)`" trick was a workaround for the same problem; the
  new envelope is the proper fix. Delete the old wrapper.
- Outermost installation is **unconditional** (not gated on
  `app_debug`). Debug-mode only adds the `traceback` field.
- CLI transport unchanged. Feedback is MCP-only; CLI's
  `error: <message>` + stderr traceback already satisfies its
  contract.
- `OPERATIONAL_CONTRACTS.md` adds the wire-envelope guarantee
  to the existing "Error envelope" section, explicitly noting
  the contract is independent of FastMCP's
  `mask_error_details`.

### Unwrapped propagation

The new wrapper does NOT catch:

- `asyncio.CancelledError` — `BaseException`, naturally not
  caught by `except Exception`. Required by `operational-contracts`
  cancellation requirement.
- `KeyboardInterrupt`, `SystemExit` — `BaseException` siblings.
- `fastmcp.exceptions.FastMCPError` and subclasses — author code
  that deliberately raises `ToolError("msg")` should reach the
  wire on FastMCP's own path; double-wrapping would corrupt the
  author's message.
- `BaseExceptionGroup` containing only `CancelledError` — anyio
  task-group cancellation per Q1's hedged-request pattern. The
  wrapper checks for this case and re-raises unchanged.

## Impact

- **Affected specs**: `operational-contracts` — tightens the
  existing *Error envelope for unhandled tool exceptions*
  requirement to specify the JSON payload structure on the
  MCP wire and to specify the FastMCP-independence guarantee.
- **Affected code**:
  - `src/a2kit/packages/mcp/server.py` — new
    `_wrap_with_error_envelope`; delete `_wrap_with_debug_traceback`;
    update wrapper-chain assembly (~line 269-330).
  - `src/a2kit/exceptions.py` — no new classes (the new wrapper
    re-raises `ToolError`).
  - `OPERATIONAL_CONTRACTS.md` — update Q5 / Error envelope.
  - `tests/test_wire_error_envelope.py` — new file. Cases:
    `ValueError` over MCP returns `{class, message}`;
    `App(debug=True)` adds traceback; author-raised `ToolError`
    passes through verbatim; `CancelledError` propagates
    unwrapped.
- **APIs**: NON-BREAKING for user code. BREAKING for any
  consumer programmatically depending on the bare
  `"Error calling tool 'X'"` string format — they SHOULD have
  been parsing structured errors all along, per the existing
  spec requirement that was unimplemented.
- **Dependencies**: none.
- **CI cost**: 4 in-memory FastMCP tests; negligible.
- **Risk**:
  - FastMCP's `FastMCPError` import path could change across
    minor versions. Mitigated by importing at module top with
    a fail-loud `ImportError` (the FastMCP version is pinned
    in `pyproject.toml`).
  - JSON-encoding the message could break consumers that
    parse the bare-string format. Acceptable — they were
    already misusing the wire per the existing requirement.
- **Out of scope**: CLI error rendering (stderr traceback +
  non-zero exit code stays unchanged); FastMCP version
  upgrade.
- **Synergy with fix-mcp-dispatch-strips-ctx**: once both ship,
  the `TypeError: missing 'ctx'` regression that motivated
  round-8 surfaces over MCP with full class+message diagnostic
  instead of the bare `"Error calling tool 'X'"`, even if a
  future regression re-introduces the same bug. Self-diagnosing
  failure mode.
