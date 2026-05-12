# Expose MCP-wire-encoded payload from the in-process test client

## Why

`a2kit.testing.client(app).invoke(...)` returns the raw Python value
the tool body produced. The CLI and MCP transports do not return that
value: they run it through `a2kit.packages.formatter.format_response`
with a `format_hint` derived from the tool's return-type annotation
(see `type-driven-format-routing`), which produces JSON, TSV, or the
`page-tsv` hybrid envelope.

Result: tests that need to assert on the wire payload — the exact
bytes / dict shape an out-of-process MCP client would receive — cannot
use the in-process client. The current workaround is to spin up the
server over real stdio (`a2web serve` etc.) and round-trip through a
real `fastmcp.Client`. Round-6 friction 2 in the a2web feedback flags
about five tests in that repo doing exactly this just to assert
formatter output.

The existing `client.render_as(fmt, value)` is close, but it forces
the test to manually pass the format hint. That couples the test to
the routing rules instead of asserting that the runtime applies them.
A test that says `render_as("tsv", result)` cannot fail when the
tool's return annotation drifts from scalar-only `list[T]` to
`list[T-with-nested]`; the production wire format would silently flip
to JSON, the test would still pass.

The fix: a sibling method `await client.call_wire(tool, ...)` that
runs the same dispatch path as `invoke`, then feeds the result
through `format_response` with the **tool descriptor's** cached
`format_hint` — exactly the call path the in-process MCP runtime
uses. The returned payload is the wire-encoded value (dict for JSON,
str for TSV, str for page-tsv) — byte-identical to what an
out-of-process MCP client would receive on the structured-content
channel.

## What Changes

### Public API — additive

`TestClient` gains one async method:

```python
async def call_wire(
    self,
    tool_name: str,
    *,
    connection: str | None = None,
    **kwargs: Any,
) -> Any: ...
```

It dispatches `tool_name` identically to `invoke` (same DI, same
lifecycle, same capture surfaces), then encodes the return value via
`format_response(value, format_hint=descriptor.format_hint)` — the
same cached hint the production dispatcher feeds the formatter — and
returns `response.data`.

Existing surfaces stay unchanged:

- `invoke(...)` continues to return the raw Python value (no
  formatter pass). Tests asserting on domain objects keep working.
- `render_as(fmt, value)` continues to take an explicit format hint
  for tests that want to compare a value against multiple encodings
  or force a non-default format. It remains useful as a low-level
  helper; `call_wire` is the high-level "what would the MCP client
  see" call.

### Surface choice: option (b) `call_wire`

The brief considers three shapes:

- (a) Opt-in flag `await c.call("tool", wire=True)` — same method
  returns either a Python object or wire payload depending on a
  kwarg. Rejected: overloaded return type, harder to type, harder
  to grep for in tests.
- (b) Sibling method `await c.call_wire(...)`. Chosen: separate
  return-type, greppable, no kwarg pollution on `invoke`.
- (c) Wrapping return `result = await c.call(...); result.wire,
  result.value`. Rejected: every existing call site would need to
  unwrap `.value`, breaks every existing test for cosmetic gain.

Naming: `call_wire`, not `invoke_wire`. `invoke` is the existing
verb; rather than chain a suffix onto it we promote the wire-aware
path to a sibling. The pair reads naturally — `invoke` returns what
the tool returned, `call_wire` returns what the wire would carry.

### Format auto-detection

`call_wire` does not re-run any type-inference heuristic. The tool
descriptor produced at registration time already carries
`format_hint` (per `type-driven-format-routing` →
"Auto-format consults the cached descriptor hint"). `call_wire`
reads `descriptor.format_hint` and passes it through to
`format_response`. If the descriptor's hint is `"auto"` for any
reason, `format_response` falls back to its own inference, matching
production behaviour.

This means a test using `call_wire` cannot diverge from the
production format choice: changing a tool's return annotation from
scalar-only `list[T]` to mixed `list[T-with-nested]` flips both the
production wire format **and** the test's observed payload from TSV
to JSON in lockstep.

### Capture surfaces still populate

Because `call_wire` reuses the `invoke` dispatch path, every event,
progress update, log call, and report emitted during the run lands
in `client.events` / `progress` / `logs` / `reports` exactly as it
does today. Tests can assert on the wire payload AND on captured
side-effects from the same call.

## Capabilities

### Modified Capabilities

- `in-process-test-client`: adds a `call_wire` requirement with
  scenarios for each format (JSON, TSV, page-tsv) and an
  auto-detect-from-descriptor scenario. Existing requirements
  unchanged.

## Impact

- **Affected code**:
  - `src/a2kit/packages/testing/client.py` — adds `call_wire`
    method.
  - `src/a2kit/packages/testing/__init__.py` — no change (the
    method hangs off the existing `TestClient` class).
  - Downstream repos (a2web, future projects): the ~5 a2web tests
    flagged in round-6 friction 2 can drop their stdio harness and
    call `client.call_wire(...)` instead.

- **APIs**: additive. `invoke` keeps its existing signature and
  return semantics. No migration needed for existing tests.

- **Dependencies**: none. `format_response` and the tool descriptor's
  cached `format_hint` already exist.

- **Risk**: minimal. The new method composes two existing surfaces
  (`invoke` and `format_response`); there is no new wire path. The
  only behavioural commitment is that the encoded payload byte-matches
  what an out-of-process MCP client would observe — enforced by the
  scenarios in the spec delta.

- **CI cost**: negligible. `call_wire` runs `invoke` + one formatter
  pass per call; no extra transport setup.
