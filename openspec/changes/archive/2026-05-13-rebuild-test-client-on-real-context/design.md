# Design — rebuild the in-process test client on real fastmcp.Context

## Context

The current `_CapturingContext` (in `src/a2kit/packages/testing/client.py`)
is a `StderrToolContext` subclass with an override on `_emit` that
appends rendered lines to capture lists. It never touches a real
fastmcp server, real client, or real wire format. Tests that exercise
"MCP behaviour" actually exercise the CLI stub.

`fastmcp.Client(transport=server)` is the standard way to drive a
FastMCP server in-memory — the same path fastmcp's own test suite
uses. The transport is in-process, no sockets, no subprocess, full
fidelity to the production dispatch path.

This change keeps the public `a2kit.testing.client` surface intact and
swaps the implementation. Most existing tests round-trip without
edits; a small subset that assert on the *rendered string form* of
log lines need a one-line shape adjustment.

## Goals / Non-Goals

### Goals

- Every tool dispatch in test code routes through the real FastMCP
  in-memory transport, exercising the real fastmcp.Context.
- The public API (`client(app)`, `c.invoke(...)`, `c.events`,
  `c.reports`, `c.logs`, `c.progress`, `c.render_as`) preserves
  signatures and semantics.
- Lifecycle hooks (`@app.on_startup` / `@app.on_shutdown`) run within
  the `async with client(app)` scope. Today they're silently bypassed
  by `_CapturingContext` because the stub doesn't trigger server
  lifecycle.

### Non-Goals

- Adding a CLI-mode test client. Tools targeting CLI semantics use
  `CliRunner` + `build_full_cli(app)` (the streaming_logger and
  sampling example tests already do this); not changed here.
- Subprocess transport, websocket transport, or any non-in-memory
  fastmcp transport. Out of scope.
- A "fake fastmcp.Context" capture layer. The whole point is to use
  the real one.

## Decisions

### D-CLIENT-CTOR — TestClient owns the FastMCP server + Client pair

`TestClient.__aenter__`:

```python
async def __aenter__(self):
    server = build_mcp_server(self._app)
    self._client = await fastmcp.Client(
        transport=server,
        log_handler=self._on_log,
        progress_handler=self._on_progress,
    ).__aenter__()
    return self
```

`__aexit__` mirror-shuts down both. The server is constructed once per
context-manager scope (per test); cold-start cost is ~2-5ms per scope
on M1.

### D-LOG-HANDLER — fan-out by `extra["a2kit_kind"]`

a2kit's LDD wire format puts `a2kit_kind` in `extra` for `event` and
`report`. The new `log` primitive doesn't add a kind marker (its
fields are user-facing). Routing:

```python
async def _on_log(self, message: LogMessage) -> None:
    extra = message.data or {}
    kind = extra.pop("a2kit_kind", None)
    if kind == "event":
        self.events.append(EventLine(
            name=extra["name"],
            payload=extra["payload"],
            elapsed_ms=extra["elapsed_ms"],
        ))
    elif kind == "report":
        self.reports.append(ReportLine(
            type_=extra["type"],
            payload=extra["payload"],
            elapsed_ms=extra["elapsed_ms"],
        ))
    else:
        # Plain log (from a2kit.ldd.log / .info / ... or fastmcp ctx.log)
        elapsed = extra.pop("elapsed_ms", None)
        self.logs.append(LogLine(
            level=message.level,
            message=message.text,
            fields=dict(extra),
            elapsed_ms=elapsed,
        ))
```

The dispatch is wire-shape-aware in exactly one place. If LDD adds a
fourth primitive later, only this handler changes.

### D-PROGRESS-HANDLER — append `(current, total)` tuples

`fastmcp.Client(progress_handler=fn)` invokes `fn(progress, total,
message)` per `ctx.report_progress` call. Captured as today:

```python
async def _on_progress(self, progress: float, total: float | None, message: str | None) -> None:
    self.progress.append((progress, total))
```

`message` is dropped to keep the tuple shape consumers already
depend on; if a test cares about the message, it switches to the
new `c.progress_with_message` list which captures the 3-tuple. Both
attributes are populated; tests opt in to richer shape on demand.

### D-LOGS-SHAPE — structured by default, rendered on demand

The breaking shape change. Today `c.logs: list[str]` of pre-rendered
LDD lines. New `c.logs: list[LogLine]` where:

```python
@dataclass(frozen=True, slots=True)
class LogLine:
    level: str          # "info" | "warning" | "error" | "debug"
    message: str
    fields: dict[str, Any]
    elapsed_ms: int | None
```

`c.logs_text: list[str]` is a derived property that calls
`format_ldd_line(level, message, fields, elapsed_ms)` for each — the
old rendered form, for tests that asserted on the line shape.

Migration recipe:

```diff
-assert "INFO" in c.logs[0]
+assert c.logs[0].level == "info"
# or, equivalently:
+assert "INFO" in c.logs_text[0]
```

The structured form is preferred for new tests because it asserts
intent (level, fields) rather than rendering.

### D-LIFECYCLE — server lifecycle runs in scope

`build_mcp_server(app)` builds the FastMCP server with the lifespan
wired up. Today's `_CapturingContext` never triggered the lifespan;
the test client just instantiated a stub. Switching to the real
in-memory transport means:

- `@app.on_startup` handlers run on `__aenter__`. Anything they DI-
  resolve must be available at test time.
- `@app.on_shutdown` runs on `__aexit__`. Resources are torn down per
  test scope.

Tests that depended on the lifecycle being skipped break (intended).
This is an improvement: any test that did `app.singleton(X, factory)`
and relied on the singleton being lazily initialised at first
`invoke()` call will now see the factory run on `__aenter__` if any
`@on_startup` resolves X. Tests catch this and migrate trivially.

### D-INVOKE — same call shape, real wire

`await c.invoke("tool_name", **wire_kwargs)` becomes:

```python
async def invoke(self, tool_name: str, /, **kwargs: Any) -> Any:
    result = await self._client.call_tool(tool_name, kwargs)
    return result.data if hasattr(result, "data") else result.structured_content
```

The return shape matches today's behaviour: a tool returning a
`pydantic.BaseModel` yields the model instance; a tool returning a
`dict` yields the dict. Pulled from `result.data` (fastmcp's typed
unmarshal) when available.

### D-RENDER-AS — unchanged

`c.render_as("json", value)` continues to delegate to the same
formatter. Pure utility; not a behavioural test.

## Alternatives Considered

### Alt-A — keep `_CapturingContext`, also add a real-transport client

Two test clients side-by-side. Tools targeting MCP use the new one;
tools that just want fast unit-shape capture use the legacy one.

Rejected. The whole problem is that the legacy client lies about
MCP behaviour. Keeping it around preserves the failure mode for
anyone who picks the wrong client. One client, real transport,
forced honesty.

### Alt-B — leave `_CapturingContext`, write a separate
"MCP-transport-smoke" helper that consumers opt into

Path of least disruption. Tests stay on the CLI subclass; an
optional sidecar test runs the real transport on a subset of tools.

Rejected. Drift hides in the gap between sidecar coverage and main
test coverage. The `field-logging-via-ldd` bug shows the cost of an
optional safety net: nobody opts in until it's too late.

### Alt-C — keep `c.logs: list[str]` as the public shape

Either render at capture time (drop the structured fields) or
double-store (rendered + structured).

Rejected. Rendering at capture time throws away the fields that make
the structured form valuable; double-storing is bloat. The migration
is `c.logs_text` for tests that need rendering — a one-line ergonomic
property, not duplication.

## Open Questions

1. **In-memory FastMCP transport edge cases**: does
   `fastmcp.Client(transport=server)` propagate exceptions raised in a
   tool body back to the client as `ToolError`, or does it surface them
   as Python exceptions on the `await call_tool(...)` line? The current
   `_CapturingContext` re-raises directly; if the new client wraps in
   `ToolError`, tests that `pytest.raises(MyError)` need a wrapper-aware
   helper. **Resolved (phase 0, 2026-05-14)**: exceptions surface as
   `fastmcp.exceptions.ToolError` carrying the a2kit-owned structured
   envelope from `mcp-structured-wire-error-envelope`. Body:
   `json.loads(str(exc)) == {"class": ..., "message": ..., [traceback]}`.
   Tests asserting on Python exception classes must parse the envelope
   or use `raise_on_error=False`.

2. **Sinks**: today, sinks registered on `app.ldd.add_sink(...)` fire
   per-emission. Under the new client, fan-out still happens (sinks
   are server-side, server is real). Confirmed compatible; just
   verify in phase 0.

3. **Cancellation semantics**: `asyncio.CancelledError` inside a
   tool body — does the in-memory transport pass it through cleanly,
   or wrap it? The cold-start tests' cancellation scenarios
   (`tests/test_spike_cancellation_flush.py`) are the canary.
   **Pending validation against the canary suite.**

4. **Should `c.logs` include LDD lines emitted by `a2kit.ldd.event` /
   `report`**, or only those emitted by `a2kit.ldd.log` and bare
   `ctx.log` / `ctx.info`? Today the lists are disjoint by `a2kit_kind`
   marker; new client preserves this. Document explicitly so test
   authors don't assert against the wrong list.

## Phase-0 Findings — design blockers uncovered 2026-05-14

A speculative implementation pass (reverted) attempted swapping
`TestClient` to a real `fastmcp.Client(transport=build_mcp_server(app))`
keeping the dict-shaped capture surfaces unchanged. The pass surfaced
two blocking issues this design does not yet resolve:

### Blocker P0-1 — typed-return marshaling differs from raw Python

The legacy `_invoke_through_dispatcher` returns the tool's raw Python
value (e.g. a `list[Root]` of user-declared dataclasses). The new
client receives `result.data` from `fastmcp.Client.call_tool`, which
is the **FastMCP-unmarshaled** form — a Pydantic-validated copy that
synthesizes types from the tool's return annotation. For
`tests/test_in_process_client.py::test_invoke_returns_value`:

```
expected = [_Item(id=1, name='alpha'), _Item(id=2, name='beta')]
got      = [Root(id=1, name='alpha'),  Root(id=2, name='beta')]
                ↑ FastMCP-synthesized type with identical fields
```

The user-declared type `_Item` and the FastMCP-synthesized `Root` are
field-equivalent but not identity-equal. Every test asserting on
`isinstance` or exact class will break. This is a real semantic
shift, not a migration hint.

**Resolution options** (decision needed before phase 1):

- **(A)** Document the semantic shift as intentional; migrate tests
  to compare by `model_dump()` or field-wise equality. Honest about
  the wire round-trip; preserves the "real transport" goal.
- **(B)** Hybrid client: drive notifications/logs through the real
  transport (so capture surfaces exercise the wrapper chain) but
  return the raw Python value via a side-channel. Loses some fidelity;
  preserves test ergonomics.
- **(C)** Don't rewrite `invoke()`; keep the dispatcher-direct path
  for return values, only wire `log_handler`/`progress_handler` to
  the real transport for emissions. Smallest change, but `invoke()`
  itself never exercises the MCP wrapper chain (defeats the original
  goal for transport-parity assertion).

### Blocker P0-2 — `ldd.event` over real MCP crashes on `name` field

`a2kit.ldd.event` emits via `ctx.log(extra={"a2kit_kind": "event",
"name": ..., "payload": ..., "elapsed_ms": ...})`. FastMCP's
`ctx.log` implementation calls
`to_client_logger.log(level=..., msg=..., extra=data.extra)` as a
server-side side effect before sending the notification. Python's
`logging.makeRecord` rejects `extra` containing `name` (reserved
`LogRecord` attribute), raising
`KeyError: "Attempt to overwrite 'name' in LogRecord"`. The
exception then propagates as a `ToolError` on the wire.

The legacy `_CapturingContext` masked this entirely by intercepting
`_emit` directly before fastmcp's logging pipeline. Every test that
exercises `ldd.event` over the real transport hits this. The
existing `test_field_logging_mcp_path.py` doesn't hit it only because
its tools use `ldd.info` (no `name` field), not `ldd.event`.

**Resolution options** (decision needed before phase 1):

- **(A)** Fix `a2kit.ldd.event` to use a non-reserved key in `extra`
  (e.g. rename to `event_name`); update spec scenarios in
  `mcp-context-passthrough` that say `data["name"]`. Out of scope
  for this change; would belong in a follow-up to
  `field-logging-via-ldd`.
- **(B)** Prefix all a2kit-internal keys in `extra` with `a2kit_`
  (`a2kit_name`, `a2kit_payload`, `a2kit_elapsed_ms`). Safer against
  the full LogRecord reserved set; same scope concern as (A).
- **(C)** Sanitize at the wire-emit site by inserting a `logging.Filter`
  that rewrites reserved keys before they reach `makeRecord`.
  Doesn't change the wire shape consumers see. Possibly the cleanest
  fix; needs a probe pass.

### Decisions (made 2026-05-14)

**P0-1 — Option (A) chosen.** Embrace FastMCP's typed-return marshaling
as the documented shape of `c.invoke()`. Tests that asserted on
identity-equal user-declared dataclasses migrate to either
`model_dump()` comparison, field-wise comparison, or `result_pydantic_model.id == 1` style attribute checks. Empirically (phase-0 probe)
this affects exactly one existing test
(`tests/test_in_process_client.py::test_invoke_returns_value`); the
migration is one assertion change. The benefit is full real-wrapper-
chain coverage for every consumer of the test client, end-to-end with
zero side-channels.

**P0-2 — Option (B) chosen.** Prefix all a2kit-internal keys in
`ctx.log(extra=...)` payloads with `a2kit_` to dodge Python's
`LogRecord` reserved-attribute set. Affects three sites in
`src/a2kit/packages/ldd/__init__.py`:

- `event` path: `name` → `a2kit_name`, `payload` → `a2kit_payload`,
  `elapsed_ms` → `a2kit_elapsed_ms`, `a2kit_kind` stays.
- `report` path: `type` → `a2kit_type`, `payload` → `a2kit_payload`,
  `elapsed_ms` → `a2kit_elapsed_ms`.
- `log` path: only `elapsed_ms` → `a2kit_elapsed_ms` (user-supplied
  fields stay un-prefixed; users sanitizing their own keys is on them,
  not the framework).

The capability spec scenarios in `mcp-context-passthrough` that
literally say `data={"name": "api.fetched", ...}` are stale — they
were never actually deliverable because the wire emit crashed. The
spec delta in this change updates them to match the new prefixed
wire shape.

The test client's `_on_log` handler reads from the prefixed keys and
maps them back to the public capture shape (`c.events[0]["name"]`,
`c.events[0]["payload"]`, etc.) so test consumers see unchanged
ergonomics. The framework owns the prefix-prefix-unprefix dance; tool
authors never see it.
