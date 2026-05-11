## Context

Origin: a2web feedback round 3, "Question — how does an external sink
subscribe to LDD emissions?" Their concrete pain: an OTel exporter that
must observe every event the orchestrator emits, regardless of which
transport (MCP / CLI / future HTTP) the App is running on.

Today's `a2kit.ldd.event()` reads a `ContextVar` (`_LDD_STATE`) set by
the dispatch site (`ldd_state_for_call` context manager), then
dispatches to one of two transports based on the runtime type of
`ctx`:

```
event(ctx, name, **payload)
   │
   ▼
   if _is_fastmcp_context(ctx):
       await ctx.log(level="info", extra={…})    ──► MCP wire
   else:
       ctx._emit("event", name, payload, …)       ──► CLI stderr
   ──► DONE. No fan-out, no observer point.
```

No place to inject an observer.

## Decisions

### D-SINK-APP-SCOPED — sinks live on `app.ldd`, not on a process-global registry

Rejected: process-global `a2kit.ldd.add_sink(fn)`. Tempting because it's
10 LOC, but two `App`s in one process would share sinks and tests would
need teardown discipline they don't currently need. App-scoped sinks
follow the v0.24/v0.25 "App owns its world" principle.

The `_AppLdd` namespace (already mounted on `App` as `app.ldd`) is the
right home: it already exists for exactly this kind of extension, and
adds zero new top-level surface.

### D-SINK-WIRING — sinks ride the existing `_LddState` ContextVar

Rather than have `event()` reach for the App through some global
registry, the dispatch sites (CLI runtime + MCP middleware) already
construct `_LddState` per call via `ldd_state_for_call(…)`. Extending
`_LddState` to carry `sinks: tuple[LddSink, ...]` and having the
dispatch sites pass `app.ldd.sinks` into the context manager is the
zero-new-plumbing path.

```
App startup:
    app.ldd.add_sink(otel_sink)
        ──► appends to app.ldd._sinks list

Tool dispatch:
    with ldd_state_for_call(..., sinks=app.ldd.sinks):
        await tool(...)
            ──► event(ctx, ...) reads _LddState.sinks, fans out

Tool returns / aborts:
    context manager resets _LddState
```

This composes cleanly with the existing kill-switch semantics
(`--no-events`, `A2KIT_LDD=off`) — those continue to gate the wire
emit AND the sink fan-out symmetrically.

### D-SINK-SIGNATURE — async callable taking `LddEmission`

Considered:

1. **Sync callable** — blocks emission, terrible for OTel exporters
   that may flush to network.
2. **Async callable** — matches `event()`/`report()`'s own async
   nature; minimal protocol surface; OTel exporters tend to be
   async-friendly.
3. **Object with `on_event`/`on_report` methods** — verbose for
   simple sinks; useful when a sink wants different behavior per
   kind, but easy enough to dispatch on `emission.kind` from inside
   an async callable.

Picked (2). The protocol is one line:

```python
class LddSink(Protocol):
    async def __call__(self, emission: LddEmission, /) -> None: ...
```

### D-EMISSION-SHAPE — frozen dataclass with both payload dict and ctx

```python
@dataclass(frozen=True, slots=True)
class LddEmission:
    kind: Literal["event", "report"]
    name: str                  # event name or report type name
    payload: dict[str, Any]    # already model_dump'd if from typed event
    elapsed_ms: int
    tool_name: str | None
    ctx: Any
```

`payload` is the already-dumped dict (so sinks don't need to know
Pydantic). `ctx` is the live ctx — sinks that want to call
`ctx.report_progress` or do their own logging can.

Open consideration: carrying a `model: BaseModel | None` for sinks that
want the typed object back. Deferred — `payload` covers the
serialization use case (OTel, NDJSON), and a sink that wants the model
can register it via the typed-event registry separately.

### D-ERROR-ISOLATION — sink exceptions are swallowed + logged

A bad sink must never break tool dispatch. The fan-out loop:

```python
for sink in state.sinks:
    try:
        await sink(emission)
    except Exception:                       # noqa: BLE001
        logger.exception("LDD sink failed", extra={"sink": sink})
```

Logging to stdlib `logger` (not `event()`, which would recurse).
`extra` carries the sink reference for debugging.

### D-FAN-OUT-ORDER — sequential awaited, not parallel

```python
for sink in state.sinks:
    await sink(emission)        # one at a time, in registration order
```

Rejected parallel (`asyncio.gather`): adds complexity, masks ordering
bugs, and OTel exporters batch internally so per-emit cost is small.
If a single slow sink becomes a problem in practice, parallel fan-out
can be opted into per-sink with a `parallel=True` kwarg later — but
that's a v0.27 conversation.

### D-CANCELLATION-FLUSH — spike first, then commit

When `anyio.fail_after` raises during a tool call, what happens to:

- The wire emit currently in-flight inside `event()` (the `await ctx.log(...)`).
- The sink fan-out loop (more `await`s, more cancellation points).

Plausible outcomes from the spike:

1. **Everything flushes cleanly.** anyio's cancellation timing is
   well-behaved here and the existing `_emit` / `ctx.log` paths complete
   before the cancellation surfaces. Document, no code change.

2. **Some emits drop.** Need a shielded scope around the inner emit
   sequence. Smallest possible:

   ```python
   with anyio.CancelScope(shield=True):
       # wire emit + sink fan-out
   ```

   Costs: a slow/hung sink could now delay timeout surfacing. Mitigate
   by adding a per-fan-out budget (`anyio.fail_after(0.5)` inside the
   shield), with a logger.warning on overrun.

3. **Wire emit drops but sinks succeed (or vice versa).** Asymmetric;
   the contract should make symmetric the default. Same shield as (2),
   covering both halves.

Decision: spike before committing to a contract. The proposal text
documents the spike as a precondition to declaring the change complete.

### D-CONNECTIONS-TO-PLUGIN-CHANGE — independent of router-as-plugin

This change does not depend on `router-as-plugin-with-surfaces`. They
can land in either order. Sinks are an `App` capability; plugin-shape
changes are an installation-surface change. No code overlap.

## Risks / open questions

- **Sink lifecycle.** A sink may need to flush at App shutdown (e.g.
  OTel batch exporter). Current design says: register a shutdown hook
  separately via `@app.on_shutdown`. Considered baking `aclose()` into
  the `LddSink` protocol; rejected as overdesign — most sinks won't
  need it, the ones that do can use existing lifecycle.
- **Sink-emitted events.** A sink that calls `event(...)` from inside
  its body would recurse. Document: sinks must not emit via the LDD
  API. Add a check (re-entrancy flag in `_LddState`?) only if real
  abuse appears.
- **Performance under many sinks.** With N sinks and M emits per tool
  call, fan-out cost is O(N·M). For the foreseeable use case (1–3
  sinks, dozens of emits per call), this is in the noise. If somebody
  attaches 50 sinks, parallel fan-out is the answer; not a v0.26
  concern.
