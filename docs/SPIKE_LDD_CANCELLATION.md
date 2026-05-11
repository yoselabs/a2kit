# Spike: LDD cancellation flush

## Question

When `anyio.fail_after` raises mid-tool, do LDD events emitted before the
timeout land on the wire (CLI stderr, MCP notifications) and on any
attached sinks? Or does cancellation propagation drop the most recent
emit(s)?

## Setup

`tests/test_spike_cancellation_flush.py` — a stub body emits 20 events at
0.05s intervals inside `anyio.fail_after(0.3)`. The test asserts that at
least 3 events landed on stderr before the TimeoutError surfaced.

## Result

**Pass.** Events emitted at `t < 0.3s` land synchronously on stderr;
the TimeoutError propagates cleanly with no masking. Roughly 6 emissions
landed in the 0.3s window, matching the expected emit cadence.

## Analysis

- **CLI path.** `StderrToolContext._emit` uses `print(..., flush=True)`
  on `sys.stderr` — a synchronous operation. Once the `await ldd_event(...)`
  returns, the bytes have already left the process. There is nothing
  in-flight to lose. Future emits never start because the next
  `anyio.sleep(0.05)` raises CancelledError, but every emit that *did*
  start has already completed.

- **MCP path.** `ctx.log(...)` is async, but FastMCP's notification dispatch
  to a connected client (or the in-process test client) is similarly fast:
  the await returns once the notification is queued on the transport, and
  cancellation strikes during the next `await anyio.sleep(...)` rather
  than mid-`ctx.log`.

- **Sink fan-out (planned).** Sinks are async callables iterated
  sequentially after the wire emit. A sink that itself awaits I/O could
  be mid-flight when cancellation arrives, and that one sink invocation
  would raise CancelledError. The sinks that already completed are not
  affected; the in-flight sink loses *this one emission*, and the
  cancellation propagates cleanly.

## Decision

**No shielded scope** around the emit / fan-out sequence.

a2web's feedback (round 3, Q5) explicitly tolerates loss: "ok if we will
send like 10 messages out of 20." Adding `anyio.CancelScope(shield=True)`
would only matter if a sink had to *complete* despite cancellation,
which is a stronger contract than any of the planned use cases require.

The contract documented in OPERATIONAL_CONTRACTS Q6:

> LDD events emitted at `t < timeout` arrive at sinks and the wire. The
> emission in-flight when cancellation fires may be dropped at the sink
> that was mid-await. For guaranteed delivery, sinks should be
> synchronous-fast (push to a queue, return immediately) and process
> out-of-band.

Sinks needing flush-on-shutdown have the existing `app.on_shutdown`
lifecycle as their tool.

## Follow-up

None. The Phase 4 implementation proceeds with a plain `for sink in
state.sinks: await sink(emission)` loop, no shield.
