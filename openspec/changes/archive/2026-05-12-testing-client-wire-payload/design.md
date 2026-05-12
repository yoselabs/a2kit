# Design — call_wire on the in-process test client

## Context

Two existing surfaces frame the design:

- `TestClient.invoke(tool, **kwargs)` runs the full dispatcher and
  returns the tool's raw Python return value. No formatter pass.
- `TestClient.render_as(fmt, value)` runs an arbitrary value through
  `format_response(value, format_hint=fmt)`. It requires the caller
  to pass `fmt` explicitly.

Production transports (CLI, in-memory MCP, stdio MCP) all route
through `format_response`, with `format_hint` resolved from the tool
descriptor's cached `format_hint` field — computed once at tool
registration by `_infer_format_hint(return_type)`. See the
`type-driven-format-routing` capability spec.

The gap: there is no test surface that **combines** dispatch and the
descriptor-driven formatter pass. Tests either get the raw Python
value (`invoke`) or hand-pick a format hint (`render_as`).

## Decision

Add a third surface to `TestClient`:

```python
async def call_wire(
    self,
    tool_name: str,
    *,
    connection: str | None = None,
    **kwargs: Any,
) -> Any
```

Implementation (single composition, no new logic):

1. Resolve the descriptor via the existing `_descriptor(tool_name)`
   private method.
2. Read `hint = descriptor.format_hint` (already cached per
   `type-driven-format-routing`).
3. Run `value = await self.invoke(tool_name, connection=connection,
   **kwargs)` — reuse the existing dispatch + capture path verbatim.
4. Return `format_response(value, format_hint=hint).data`.

Return type is `Any` — the wire payload type varies per format:

- `"json"` → dict (or list/scalar; whatever the value JSON-encodes
  to).
- `"tsv"` → str (the TSV table, including header).
- `"page-tsv"` → str (the JSON envelope with embedded TSV `items`).

This matches what `render_as` already returns today (the `.data`
field of the `Response` object).

## Alternatives considered

### (a) `await c.call("tool", wire=True)` — opt-in flag

Rejected. Pros: only one entry point to learn. Cons:

- Return type becomes a union of `Any` (raw object) and the wire
  shape. Type checkers cannot narrow.
- Every existing call site to `invoke` (~60 occurrences across the
  test suite) now has a phantom kwarg it must remember to omit.
- Worse to grep — `git grep call_wire` finds wire-mode tests
  precisely; `git grep "wire=True"` is noisier.

### (c) Wrapping return `result.wire, result.value`

Rejected. The unwrap tax on existing tests is high (every `await
c.invoke(...)` becomes `(await c.invoke(...)).value`) for a gain
that only matters to the small set of tests that need both
representations of the same call. Those tests can issue two calls
or read `client.events`/`reports` for side-effect channels.

### Reuse `render_as` with descriptor lookup at call site

Tests could do `c.render_as(c._descriptor(name).format_hint, value)`.
Rejected: leaks the private `_descriptor` lookup, requires the test
to know about format-hint caching, and provides no enforcement that
the format actually matches production routing.

## Format auto-detection

`call_wire` does not implement format inference. It reads the
descriptor's cached `format_hint`, which is the same value the
production dispatcher passes to `format_response`. If a tool's
return annotation changes (e.g., a model field gains a nested
model), the descriptor's `format_hint` flips at registration time,
and `call_wire` observes the new format on the next call — exactly
the production behaviour.

If `descriptor.format_hint` is `"auto"` (the documented sentinel for
"let the formatter decide"), `format_response` falls back to its own
inference. `call_wire` passes `"auto"` through verbatim; no special
case.

## Naming for the structured-content carrier

The MCP wire splits content across two channels: `content` (legacy
text) and `structuredContent` (the typed payload). `format_response`
returns a `Response` object with a `.data` field that is the
structured-content payload. `call_wire` returns exactly `.data` —
the structured-content view, which is what tools care about for
assertion.

The method name avoids "structured" / "structured_content" because
the formatter already abstracts the channel split; "wire" is the
right level — what travels over the wire as the typed payload.

## Open questions

None. The change is a pure composition of two existing surfaces;
all routing decisions are already pinned by
`type-driven-format-routing` and `cli-response-encoding`.

## Invariants this change preserves

- `invoke` behaviour: unchanged. Returns raw Python values.
- `render_as` behaviour: unchanged. Manual-format helper remains.
- `events` / `progress` / `logs` / `reports` capture: unchanged.
  `call_wire` reuses `invoke`'s dispatch, so capture surfaces
  populate identically.
- Format routing: unchanged. The descriptor's cached `format_hint`
  drives both production transports and `call_wire`.
