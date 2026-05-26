## Why

a2kit BACKLOG has an "LDD reshape" item that names the trigger
explicitly: *"second tool starts wanting structured operator-side
logs, OR a2web's `otel_sink` grows enough that promoting it to
framework default becomes obviously right."*

Both conditions are now met (or near-met):

1. **a2web has shipped `otel_sink`** (`src/a2web/events/sinks.py`)
   that subscribes to `a2kit.packages.ldd.LddEmission`, emits one
   OTel span per `*Ended` event, and degrades silently when the
   SDK is absent. It is in production, registered via
   `app.ldd.add_sink(otel_sink)` in `server.py`. The pattern is
   ~50 LOC of stable code that every other a2kit consumer also
   wants the moment they ship to a real environment.

2. **a2web's `bench-live-sink-v1`** (in-flight, openspec change)
   adds a `LiveSink` that subscribes to `CellStarted`/`CellEnded`
   events and renders one stdout line per event under an
   `asyncio.Lock`, plus a 30s heartbeat showing running/done/cost.
   The pattern generalises: any long-running multi-cell task
   (eval runs, batch ingestions, parallel API calls) wants the same
   in-flight visibility instead of the silent-then-dump shape.

3. **The call-site census** in the BACKLOG already records:
   `report()` has zero callers; `log()`/`info`/`warning`/`error`/`debug`
   have zero callers; `event()` is used only by a2web (heavy, typed).
   The current LDD primitives over-encode for what consumers
   actually do — emit structured events, want them rendered.

The reshape the BACKLOG sketches is Path B (keep current shape,
promote operator sinks to first-class) — Path A (`emit()` fusion)
is a bigger surface break and Path C (defer) loses the moment.
**This change picks Path B**: the primitives stay, but the
operator/wire fan-out becomes first-class, and `otel_sink` +
`live_sink` ship in-framework as opt-in defaults.

The naming concession in the BACKLOG ("drop 'LDD' branding in
prose") is honoured: spec and docs SHALL use "emission channel" /
"operator sink" / "wire sink" in user-facing prose. The package
keeps the `ldd` name for surface stability — renaming the public
import path is a separate decision with its own cost.

## What Changes

- New explicit operator/wire split in the LDD package:
  - **Wire sink** — the MCP `ctx.log` / FastMCP `Context` path that
    forwards emissions to the connected client. Today this is the
    only path; it stays unchanged in behaviour, but the spec names
    it as one of two channels.
  - **Operator sinks** — `state.sinks` list (already present)
    becomes the documented channel for stderr / OTel / file
    consumers. Fan-out to operator sinks is parallel and
    independent of wire-sink success.
- New built-in operator sinks shipped under `a2kit.packages.ldd`:
  - `stderr_pretty_sink` — one human-readable line per emission to
    stderr, optional ANSI colour, level-aware.
  - `stderr_json_sink` — one JSON-line per emission to stderr (one
    record per line, compatible with `jq` / log shippers).
  - `otel_sink` — lifted near-verbatim from a2web's
    `src/a2web/events/sinks.py`; emits one OTel span per `*Ended`
    event, drains every emission when the SDK is absent.
  - `live_sink` — lifted from a2web's `bench-live-sink-v1`; one
    line per `*Started`/`*Ended` pair under an asyncio.Lock, plus
    a configurable heartbeat (default 30s) showing running/done.
- New `LddConfig` knobs (or env equivalents under existing
  `A2KIT_LDD__` prefix):
  - `LDD_STDERR_SINK` ∈ `none | pretty | json` (default `none` —
    preserves current behaviour).
  - `LDD_OTEL_SINK` ∈ `auto | on | off` (default `auto` — registers
    `otel_sink` iff OTel SDK is importable AND `OTEL_EXPORTER_*`
    env present).
  - `LDD_LIVE_SINK` ∈ `off | on` with `LDD_LIVE_HEARTBEAT_SECONDS`
    (default `off`, `30`). Live sink is opt-in because it's noisy.
- Spec gain: every operator sink MUST be a pure async consumer; it
  MUST drain every emission even when its backend is unavailable
  (mirroring `otel_sink`'s "no-op consumer when SDK missing"
  invariant). The producer SHALL never block on a sink failure.
- Spec gain: the wire sink failure SHALL NOT abort operator
  fan-out, and an operator sink failure SHALL NOT abort the wire
  sink or other operator sinks.
- The "LDD" branding stays in code (`a2kit.packages.ldd`,
  `LddEmission`, `LddConfig`) for stability; user-facing prose in
  the spec and `docs/patterns/` uses "emission channel" /
  "operator sink" / "wire sink".
- a2web's `otel_sink` becomes a one-liner registration
  (`app.ldd.add_otel(...)` or env-driven auto) instead of a
  hand-ported function in its repo. Migration is a follow-up in
  a2web, not in this change.

## Capabilities

### New Capabilities
- `ldd-operator-sinks` — built-in stderr / OTel / live sinks,
  config-driven registration, failure-isolation contract.

### Modified Capabilities
- `ldd-level-threshold` — clarifies that the threshold filter runs
  ONCE at the primitive, before operator AND wire fan-out; an
  emission accepted by the threshold reaches both channels.
- `otel-adapter` — the OTel sink moves from "consumer concern" to
  "framework default (opt-in via config)"; the spec adds the
  drain-on-unavailable invariant.

## Impact

- Affected code: new `src/a2kit/packages/ldd/sinks/` subpackage
  (4 sink files + `__init__.py`), new `LddConfig` fields, runtime
  registration in `App` boot that reads config and registers the
  enabled built-in sinks before user-added sinks.
- No breaking change to the existing `app.ldd.add_sink(callable)`
  API. No change to `LddEmission` shape. No change to wire
  semantics. Pure additive surface.
- a2web's `events/sinks.py` becomes redundant once this lands;
  a2web migration to `app.ldd.add_otel()` (or env-driven auto)
  is a follow-up.
- Cross-ref: BACKLOG "LDD reshape" entry, a2web archived change
  `openspec/changes/archive/2026-05-25-fetcher-orchestrator-refactor-v1/`
  (where `events/sinks.py` matured), a2web in-flight change
  `openspec/changes/bench-live-sink-v1/`.

## Non-goals

- **Not** fusing `event()`/`log()`/`report()` into one `emit()`
  primitive (Path A in the BACKLOG). Defer until the call-site
  census changes — today the primitives match how a2web actually
  writes code.
- **Not** renaming the `ldd` package or `LddEmission` type. The
  prose-level rebrand to "emission channel" is sufficient.
- **Not** changing the wire path. FastMCP `ctx.log` semantics stay
  exactly as they are.
- **Not** porting every existing sink in a2web. This change adds
  framework-side defaults; a2web's consumer-side migration is a
  separate change in that repo.
