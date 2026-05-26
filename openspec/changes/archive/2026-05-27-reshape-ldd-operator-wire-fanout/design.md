## Design notes — LDD operator/wire fan-out + default sinks

### Why Path B (promote sinks) over Path A (fuse `emit()`)

The BACKLOG sketches three candidates. Path A (fuse `event`/`log`
into one `emit()` primitive, drop boolean kill-switches, ship
operator sinks) is the largest surface change. Path B keeps the
primitives, splits the fan-out. Path C defers.

The empirical case for B over A:

- `event()` is used heavily in a2web — typed, named events with
  rich payloads. Fusing into `emit("CellStarted", **payload)`
  loses the type story `event(CellStarted(...))` enables.
- `log()` / `info()` / `warning()` / `error()` / `debug()` have
  zero callers across the consumer survey. Removing them is fine,
  but a separate, smaller change can do it without bundling.
- The operator/wire-channel separation is the real consumer pain
  (a2web reimplemented stderr+OTel; future consumers will too).
  That pain is orthogonal to the primitive shape.

Conclusion: split the fan-out now (high-leverage), defer the
primitive fusion (orthogonal, can ship independently if call-site
census ever changes).

### Operator/wire fan-out semantics

```
                  ┌──────────────────────────┐
                  │   primitive call         │
                  │   (event / log / debug)  │
                  └──────────────┬───────────┘
                                 │
                                 ▼
                  ┌──────────────────────────┐
                  │   threshold filter       │  (single volume control;
                  │   (ldd-level-threshold)  │   already specified)
                  └──────────────┬───────────┘
                       accepted  │  dropped → return
                                 ▼
                   ┌─────────────┴──────────────┐
                   │   parallel fan-out         │
                   └──────┬─────────────┬───────┘
                          │             │
                ┌─────────▼──┐    ┌─────▼──────────────┐
                │ wire sink  │    │ operator sinks     │
                │ (ctx.log)  │    │ (stderr/otel/live/ │
                │            │    │  user-added)       │
                └────────────┘    └────────────────────┘
                  one channel      N channels, parallel,
                  per request      failure-isolated
```

Failure isolation is the load-bearing invariant: a slow OTel
exporter, a missing FastMCP context, or a misbehaving user-added
sink MUST NOT block the others. Each sink runs inside
`asyncio.gather(..., return_exceptions=True)` with exceptions
logged at WARN (under `a2kit.ldd.sink_failed`) and dropped.

### Why ship four default sinks, not just OTel

The cost of one more sink is small and they answer different
operator questions:

| Sink              | Operator question answered                          |
| ----------------- | --------------------------------------------------- |
| `stderr_pretty`   | "What's happening right now?" (CLI dev loop)         |
| `stderr_json`     | "Pipe to jq / log shipper" (production w/o OTel)     |
| `otel_sink`       | "Trace + correlate across services" (production)     |
| `live_sink`       | "Long-running multi-cell task progress" (benchmarks) |

Cutting any of the four pushes that consumer back to "write your
own" — which is the failure mode a2web hit.

### `LDD_OTEL_SINK=auto` heuristic

The auto mode is registered iff *both* conditions hold:
1. `opentelemetry` is importable, AND
2. At least one `OTEL_EXPORTER_*` env var is set.

This avoids the surprise of "I imported the OTel SDK for an
unrelated reason and now my LDD output goes to nowhere." The
heuristic mirrors how many OTel-aware libraries decide whether
to wire up tracing automatically.

### Backwards compatibility

- `app.ldd.add_sink(callable)` keeps working unchanged.
- The default config (`LDD_STDERR_SINK=none`, `LDD_OTEL_SINK=auto`,
  `LDD_LIVE_SINK=off`) preserves today's behaviour for any consumer
  that hasn't opted into the auto-OTel mode by importing the SDK.
- The wire sink (`ctx.log`) keeps emitting exactly the same
  payloads — no MCP envelope change, no `dur_ms`/`t_ms` semantics
  change. The spec just names this channel.

### Why no rename

Renaming `a2kit.packages.ldd` → `a2kit.packages.emit` (or any
variant) is a public surface break for every consumer.  Cost
exceeds clarity gain — operators read prose, not import paths.
Prose uses "emission channel" / "operator sink" / "wire sink";
code keeps `Ldd*` names. Reconsider only if a separate v1.0
public-surface review revisits the package layout en masse.

### What `live_sink` ports from a2web verbatim

- One stdout line per `*Started`/`*Ended` event pair.
- 30s heartbeat (configurable) showing `running: K, done: N/total`.
- `asyncio.Lock` around stdout writes so concurrent cells don't
  interleave.
- Cost-tracking field (`cost: $X.XX`) is a2web-specific and does
  NOT port — the in-framework version is generic over payload
  fields, and cost-display is reintroduced on the a2web side via
  a small subclass or a payload formatter callable.

### Open question (resolve before tasks)

Should `live_sink` event-name filter be configurable (today
a2web hard-codes "CellStarted"/"CellEnded")? Recommendation:
yes — the framework version takes `event_prefixes=("Cell",)`
defaulting to `("",)` (i.e. all `*Started`/`*Ended`).
