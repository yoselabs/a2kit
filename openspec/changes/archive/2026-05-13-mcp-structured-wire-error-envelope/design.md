# Design — mcp-structured-wire-error-envelope

## Context

The existing `operational-contracts` requirement specifies a
structured error envelope on the MCP wire, but the implementation
relies on FastMCP's `mask_error_details` semantics which have
demonstrated drift across minors. a2kit needs to own the wire
bytes via a transport-level mechanism FastMCP cannot override.

The mechanism is the `FastMCPError` re-raise path: FastMCP's
tool-dispatch re-raises `FastMCPError` subclasses unchanged
before the masking branch runs, so `raise
ToolError(json.dumps(payload)) from exc` puts arbitrary text on
the wire verbatim.

## D-WRAPPER-LOCATION — outermost, always

The new wrapper sits where `_wrap_with_debug_traceback` sits
today (server.py:330-331), but installed **unconditionally**
(not gated on `app_debug`).

```
fn → router_enrichers → dispatch_hook → ldd_state → error_envelope
                                                     │
                                                outermost
                                                     │
                                                     ▼
                                              FastMCP introspection
```

Why outermost:
- Catches exceptions from every inner wrapper (router enrichers
  may re-raise enriched exceptions; dispatch hook may raise
  container resolution errors; ldd state may raise during emit).
- Sees the final exception after enrichment.
- No code inside the wrapper chain needs to know about the
  envelope; the contract is "raise anything, get structured
  wire output."

`_wrap_with_debug_traceback` is deleted. Its purpose
(embed traceback in `str(exc)`) is subsumed by the new
wrapper's structured `traceback` field, which is correct JSON
shape rather than message smashing.

## D-EXCLUSION-LIST — what NOT to catch

```python
try:
    return await fn(*args, **kwargs)
except FastMCPError:
    # Author-raised ToolError or similar — passes through on
    # FastMCP's own path. Double-wrapping would JSON-encode the
    # author's message.
    raise
except BaseExceptionGroup as eg:  # anyio/asyncio cancellation aggregate
    if all(isinstance(e, asyncio.CancelledError) for e in eg.exceptions):
        raise
    # Mixed group with non-cancellation exceptions: extract the
    # first non-cancel and wrap it (rare; documented).
    non_cancel = [e for e in eg.exceptions if not isinstance(e, asyncio.CancelledError)]
    payload = _build_payload(non_cancel[0], debug=debug)
    raise ToolError(json.dumps(payload)) from non_cancel[0]
except Exception as exc:
    payload = _build_payload(exc, debug=debug)
    raise ToolError(json.dumps(payload)) from exc
```

`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit` are
`BaseException` siblings — not caught by `except Exception`.
No explicit guard needed; falls through naturally.

`BaseExceptionGroup` handling matters because of anyio
task-group patterns documented in `OPERATIONAL_CONTRACTS` Q1
(hedged requests). A group containing only cancellations must
propagate as cancellation; mixed groups extract the first
non-cancel exception.

## D-PAYLOAD-SHAPE

```python
def _build_payload(exc: BaseException, *, debug: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "class": type(exc).__name__,
        "message": str(exc),
    }
    if debug:
        payload["traceback"] = traceback.format_exc()
    return payload
```

Schema-stable: two required keys, one optional key. Documented
in `OPERATIONAL_CONTRACTS`. Consumer parsers can rely on
`json.loads(content[0].text)["class"]` and
`["message"]` always being present on `isError: true` responses.

`class` is the unqualified Python class name (`type(exc).__name__`)
not the fully qualified module path. Reason: stability across
package refactors; consumers parse by class name not module
path. Documented.

`message` is `str(exc)`. Already canonical.

`traceback` (when present) is the full
`traceback.format_exc()` output — multi-line string with
"Traceback (most recent call last):" header, file paths, line
numbers, exception line.

## D-FASTMCP-IMPORT — import at module top

```python
from fastmcp.exceptions import FastMCPError, ToolError
```

at the top of `server.py` (already imported as needed for
existing code paths). Fail-loud on `ImportError` — FastMCP is
required, pinned in `pyproject.toml`. No graceful degradation
needed.

If FastMCP renames `FastMCPError` in a future minor, the
import fails at startup with a clear error pointing at the
pinned-version mismatch — preferred over silent wrapping of
the wrong exception class.

## D-CLI-PARITY — unchanged

Consumer feedback is MCP-only. CLI's existing behavior
(`error: <message>` to stderr + traceback when `debug=True` +
non-zero exit code) satisfies the CLI side of the existing
`operational-contracts` requirement. The new requirement scopes
the structured-envelope guarantee to the MCP wire.

CLI consumers debugging by parsing stderr are unaffected.

## Alternatives considered

### Alt-1: Replace FastMCP's masking via runtime patching

Reach into `fastmcp.server.server` and monkey-patch the
dispatch function to never mask. Rejected:
- Fragile across FastMCP versions.
- Hides the dependency from readers.
- The `FastMCPError` re-raise path is documented FastMCP behavior;
  exploiting it is not a hack.

### Alt-2: Return a structured FastMCP `ToolResult` with `isError: true`

FastMCP supports `ToolResult` returns with manual `isError`
flagging. Rejected:
- More invasive (`ToolResult` requires content-block construction).
- `ToolError`-raise is the FastMCP-canonical error path; using
  it preserves the `isError: true` semantics without manual
  content construction.

### Alt-3: Gate on `app_debug`, keep `_wrap_with_debug_traceback` as the non-debug path

Rejected — the bare `"Error calling tool 'X'"` string in
non-debug mode is exactly what the round-8 feedback is asking
us to fix. Production traffic runs `debug=False` and the wire
should still carry `{class, message}` for self-reporting.

## Risks

- **JSON payload is a string inside `content[0].text`**, not a
  structured MCP content type. Consumers must `json.loads` it.
  Documented in the new spec scenario; alternative (MCP-native
  structured error type) doesn't exist in the current MCP
  protocol version.
- **Very long tracebacks** could exceed FastMCP's content-size
  budgets. Mitigated by `debug=True` being opt-in; production
  payloads (`class + message`) are typically <1KB.
- **str(exc) may contain newlines or special characters.** JSON
  encoding handles this correctly; consumers using
  `json.loads` get the raw string back. No double-escaping.

## Out of scope

- CLI envelope changes.
- FastMCP version upgrade.
- Custom error-payload extensions per-tool (would belong in
  `mcp-tool-annotations`, separate change).
