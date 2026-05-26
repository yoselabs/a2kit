# Operator and wire emission channels

a2kit's LDD primitives (`event`, `report`, `log`, `info`, `warning`,
`error`, `debug`) fan each accepted emission out to **two
independent channels**:

- **Wire sink** — the MCP `ctx.log` / FastMCP `Context` path that
  forwards the emission to the connected agent client.
- **Operator sinks** — the in-process sinks registered on
  `app.ldd.add_sink(...)` plus the built-in stderr / OTel / live
  sinks that App boot registers from `A2kitConfig.ldd.*_sink`.

A single level threshold gates both channels. Once the threshold
accepts an emission, every operator sink AND the wire path receive it
in parallel via `asyncio.gather(..., return_exceptions=True)`. A
per-sink failure is logged at WARN under `a2kit.ldd.sink_failed` and
dropped — it cannot abort sibling sinks, the wire path, or the
producer.

## The four built-in operator sinks

| Sink | Config | Operator question answered |
|---|---|---|
| `stderr_pretty_sink` | `A2KIT_LDD__STDERR_SINK=pretty` | "What's happening right now?" (CLI dev loop) |
| `stderr_json_sink` | `A2KIT_LDD__STDERR_SINK=json` | "Pipe to jq / log shipper" (production without OTel) |
| `otel_sink` | `A2KIT_LDD__OTEL_SINK=auto|on` | "Trace + correlate across services" |
| `live_sink` | `A2KIT_LDD__LIVE_SINK=on` | "Long-running multi-event task progress" |

Default config: `stderr_sink=none`, `otel_sink=auto` (registers iff
SDK + `OTEL_EXPORTER_*` env present), `live_sink=off`. The defaults
preserve existing consumer behaviour — a fresh deploy without OTel
SDK or explicit opt-in sees no built-in sinks.

## When consumers care

Most tool authors never touch the channels — the LDD primitives Just
Work and the operator picks built-ins via env. Times the channels
matter:

- **You want to ship stderr observability** without writing your own
  sink: flip `A2KIT_LDD__STDERR_SINK` to `pretty` (dev) or `json`
  (production).
- **You're integrating OTel for the first time**: install the SDK,
  set `OTEL_EXPORTER_OTLP_ENDPOINT`, and the `auto` default
  registers `otel_sink` for you.
- **You're running a long, multi-event task** (eval batch, parallel
  ingest): flip `A2KIT_LDD__LIVE_SINK=on` to get per-event progress
  lines + a heartbeat.
- **You're writing a custom sink**: keep using
  `app.ldd.add_sink(callable)`. User-added sinks run AFTER the
  built-ins in registration order, with the same failure isolation.

## Naming note

Prose uses "emission channel" / "operator sink" / "wire sink".
The package keeps the `ldd` name (`a2kit.packages.ldd`,
`LddEmission`, `LddConfig`) for surface stability — see the
`reshape-ldd-operator-wire-fanout` design notes on why no rename.

## See also

- `openspec/specs/ldd-operator-sinks/spec.md` — locked contract.
- `openspec/specs/ldd-level-threshold/spec.md` — threshold runs once.
- `openspec/specs/otel-adapter/spec.md` — OTel sink invariants.
- `src/a2kit/packages/ldd/sinks/` — the four built-ins.
