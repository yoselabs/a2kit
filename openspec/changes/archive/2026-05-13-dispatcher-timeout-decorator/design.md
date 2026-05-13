# Design — dispatcher-timeout-decorator

## D-PARSE — accept float, int, or "Ns"/"Nm"/"Nms" string

```python
def _parse_timeout(value: float | int | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    # String form.
    s = value.strip().lower()
    for suffix, mult in (("ms", 0.001), ("s", 1.0), ("m", 60.0)):
        if s.endswith(suffix):
            return float(s[: -len(suffix)]) * mult
    return float(s)  # bare number string
```

Two-letter `"ms"` checked before single-letter `"s"` to avoid
mismatch. Decorator validates at decoration time; invalid string
raises `TypeError` immediately.

## D-WRAPPER — innermost, anyio.fail_after

Wrapper-chain ordering (outermost → innermost):

```
fastmcp introspection
   ↓
_wrap_with_error_envelope    (catches TimeoutError → JSON envelope)
   ↓
_wrap_with_ldd_state         (binds ambient ctx)
   ↓
_wrap_with_dispatch_hook     (resolves DI)
   ↓
_wrap_with_router_enrichers  (router-level error enrichment)
   ↓
_wrap_with_timeout           ← NEW, innermost
   ↓
fn (tool body)
```

The timeout wrapper is innermost so:

- DI resolution doesn't count against the timeout budget (factory
  work is framework-side, not tool-author work).
- Ambient LDD scope is established before the timeout starts —
  emissions during teardown still find `_LDD_STATE`.
- Router enrichers run after the timeout fires but before the
  envelope wraps, so a Router's `enrich(exc)` method can
  customize the timeout message if it wants.

```python
def _wrap_with_timeout(fn, *, seconds: float):
    import anyio
    import functools

    @functools.wraps(fn)
    async def _wrapped(*args, **kwargs):
        with anyio.fail_after(seconds):
            return await fn(*args, **kwargs)
    return _wrapped
```

If `fn` is sync, `_wrap_with_timeout` skips the fail_after (it's
moot — sync code can't be cancelled at await boundaries).
Decorator-time check: warn if `timeout=` on a sync tool.

## D-CLI-PARITY — same wrapper at CLI dispatch site

`cli/runtime.py:_invoke_tool_in_process` calls `fn(**call_kwargs)`
directly. Adding the timeout there mirrors the MCP wrapper-chain
placement:

```python
# inside _invoke_tool_in_process, after dispatch_hook resolves kwargs:
if meta.extras.timeout_seconds is not None:
    with anyio.fail_after(meta.extras.timeout_seconds):
        raw = await fn(**call_kwargs)
else:
    raw = await fn(**call_kwargs)
```

CLI's error-handling raises `TimeoutError` to stderr (existing
non-zero-exit + traceback path). The CLI doesn't carry the
structured-envelope contract; the message is human-readable.

## D-META-SURFACE — `annotations_as_dict["a2kit"]["timeout_seconds"]`

`A2KitMeta.annotations_as_dict()` currently surfaces a subset of
the extras under the `a2kit` namespace. Add `timeout_seconds`
when set. Wire path: MCP `tool.meta` carries it; agent clients can
read `tool.meta["a2kit"]["timeout_seconds"]` to set their own retry
policy.

## D-ERROR-CLASS — Python `TimeoutError`, not asyncio's

`anyio.fail_after` raises Python's built-in `TimeoutError`
(builtins, not `asyncio.TimeoutError`). The envelope serializes it
as `{"class": "TimeoutError", "message": ...}`.

`asyncio.TimeoutError` and Python `TimeoutError` were unified in
Python 3.11 (`asyncio.TimeoutError = TimeoutError`), so consumers
checking `isinstance(exc, asyncio.TimeoutError)` work transparently.

## Alternatives considered

### Alt-A — pure sugar over `anyio.fail_after` in tool body

Rejected per the proposal's why-section. The framework coordination
(LDD scope, DI cost, annotation surfacing) is real.

### Alt-B — App(default_timeout=...) instead of per-tool

Out of scope. Per-tool is the prerequisite; App-default can layer
on top later when a consumer needs it.

### Alt-C — timeout via `ToolAnnotations`

Rejected — `ToolAnnotations` is the MCP-protocol-defined slot;
shoehorning a2kit-specific timeout there would conflict with future
upstream additions. Use the `a2kit` extras namespace.

## Out of scope

- Per-call timeout override at invocation time.
- Adaptive timeout based on payload size.
- Retry policy.
