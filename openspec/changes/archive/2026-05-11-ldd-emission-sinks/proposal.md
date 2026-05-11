## Why

a2web feedback round 3 asks: "How does an external in-process consumer
(OpenTelemetry exporter, custom NDJSON sink, anything that wants to
observe LDD emissions for its own purposes) subscribe to the emission
stream of a given App?"

Today the answer is "it can't, cleanly." `a2kit.ldd.event()` and
`a2kit.ldd.report()` dispatch directly to one of two transports — MCP
`ctx.log(extra=…)` or CLI stderr — and offer no fan-out point. Apps
that want observability outside the transport (OTel spans, audit logs,
custom metrics) must double-emit at every call site: once via a2kit,
once into a private channel.

a2web has been doing exactly this — running their own `anyio.MemoryObjectStream`
EventBus with `mcp_progress_sink` and `otel_sink` subscribers. v0.25's
typed-event registry lets them drop the progress sink (events flow
through `event(ctx, ...)` and reach MCP automatically), but the OTel
sink has no subscription point and remains stuck on the double-emit
pattern.

Every observability-tool integration (OTel, Datadog, Honeycomb,
Prometheus push gateway, plain audit logs, NDJSON exporters) will hit
the same wall. Forcing each consumer to maintain a parallel emit
channel means every a2kit-using project re-invents the same fan-out.

FastMCP middleware (the alternative discussed) only observes wire-level
notifications and is unreachable from the CLI dispatch path. For
dual-mode apps like a2web (which run both as MCP server and CLI tool),
wire middleware is a leaky abstraction.

## What Changes

### `app.ldd.add_sink(sink)` — App-scoped subscription

```python
from a2kit.ldd import LddEmission, LddSink

async def otel_sink(emission: LddEmission) -> None:
    span = tracer.start_span(f"a2kit.{emission.name}")
    try:
        span.set_attribute("kind", emission.kind)
        span.set_attribute("elapsed_ms", emission.elapsed_ms)
        for k, v in emission.payload.items():
            span.set_attribute(k, v)
    finally:
        span.end()

app.ldd.add_sink(otel_sink)
```

Sinks are async callables taking a single `LddEmission` payload:

```python
@dataclass(frozen=True, slots=True)
class LddEmission:
    kind: Literal["event", "report"]
    name: str                  # event name OR report type name
    payload: dict[str, Any]    # already-dumped JSON-compatible dict
    elapsed_ms: int            # relative to dispatch start (or process start)
    tool_name: str | None      # the dispatching tool, if any
    ctx: Any                   # live ctx — sinks may use it for progress, logs, etc.
```

### Wiring

The existing `_LddState` (a `ContextVar` set by `ldd_state_for_call`
during dispatch) grows a `sinks: tuple[LddSink, ...]` field. CLI and
MCP dispatch sites read the App's sink list and pass it into the
context-manager.

`event()` and `report()`, after emitting to the wire, iterate
`state.sinks` and await each. Fan-out is sequential. Sink exceptions
are caught and logged via stdlib `logger.exception(...)`; one bad sink
never breaks tool dispatch.

### Cancellation flush — spike + decision

There is one open question that gates declaring this complete: when
`anyio.fail_after` (or any cancellation) raises mid-tool, does the
most-recently-emitted LDD event reach attached sinks, or does
cancellation propagation drop it? This matters for a2web's
troubleshooting case: a fetch tier times out, and they need to see the
last heartbeat to know where it died.

A spike (~half-day) determines the answer. If events drop, the change
adds a small "drain on cancel" mechanism — likely a single shielded
scope around the sink fan-out — and documents the contract in
`OPERATIONAL_CONTRACTS.md` Q6.

### Documentation — Q6 heartbeat pattern

A new `OPERATIONAL_CONTRACTS.md` Q6 documents the heartbeat pattern as
the answer to "how do I get visibility during a long phase":

```python
@dataclass
class TierHeartbeat:
    step: str
    elapsed_s: float
    status: str

app.ldd.events.register(TierHeartbeat)

# In a long-running tier:
async with anyio.fail_after(60):
    async with anyio.create_task_group() as tg:
        tg.start_soon(_heartbeat_loop, ctx, "browser", interval=5)
        result = await long_running_work()
```

The combination of `add_sink` + heartbeat events + cancellation-flush
guarantees gives a2web (and any future consumer) the visibility they
need without inventing a new streaming wire format.

## Impact

### Affected code
- `src/a2kit/packages/ldd/__init__.py` — `LddEmission` + `LddSink`
  protocol; `_AppLdd` grows `add_sink` / `remove_sink` / `sinks`;
  `_LddState` grows `sinks` tuple; `event()` / `report()` fan-out loops.
- `src/a2kit/packages/cli/runtime.py` — dispatch site passes
  `app.ldd.sinks` into `ldd_state_for_call`.
- `src/a2kit/packages/mcp/server.py` — middleware dispatch site does
  the same.
- `OPERATIONAL_CONTRACTS.md` — new Q6.

### Breaking changes
None. Sinks are opt-in; absent any registered sinks, behavior is
byte-identical to v0.25.

### Migration for a2web
```diff
- # events/bus.py — delete
- # events/sinks.py — replace 96 LOC of bus glue with a single sink fn:

  async def otel_sink(emission: a2kit.ldd.LddEmission) -> None:
      ...

  # In app startup:
+ app.ldd.add_sink(otel_sink)
```

a2web's predicted ~190 LOC drop is realized; the OTel sink shrinks to
~15 LOC of pure OTel logic, no plumbing.
