## 1. BDD specs (write tests first)

- [x] 1.1 `tests/capabilities/ldd_operator_sinks/test_fanout_isolation.py` — a sink that raises does not abort other sinks or the wire path; failure is logged at WARN.
- [x] 1.2 `tests/capabilities/ldd_operator_sinks/test_threshold_runs_once.py` — a sub-threshold emission reaches NEITHER operator nor wire channels.
- [x] 1.3 `tests/capabilities/ldd_operator_sinks/test_stderr_pretty_one_line.py` — pretty sink writes one human-readable line per accepted emission; level shown.
- [x] 1.4 `tests/capabilities/ldd_operator_sinks/test_stderr_json_one_record.py` — JSON sink writes one valid JSON record per line; round-trips through `json.loads`.
- [x] 1.5 `tests/capabilities/ldd_operator_sinks/test_otel_sink_drains_without_sdk.py` — with `opentelemetry` stubbed missing, otel_sink still accepts every emission (no exception, no backlog).
- [x] 1.6 `tests/capabilities/ldd_operator_sinks/test_otel_sink_emits_span_per_ended.py` — with OTel SDK present, one span per `*Ended` event; `*Started` and heartbeats are silently drained.
- [x] 1.7 `tests/capabilities/ldd_operator_sinks/test_live_sink_heartbeat.py` — with `LDD_LIVE_HEARTBEAT_SECONDS=0.1`, the heartbeat line appears within 200ms when at least one event is in flight.
- [x] 1.8 `tests/capabilities/ldd_operator_sinks/test_live_sink_lock_no_interleave.py` — 100 concurrent emissions through live_sink produce 100 atomic lines (no character-level interleave).
- [x] 1.9 `tests/capabilities/ldd_operator_sinks/test_otel_auto_heuristic.py` — `LDD_OTEL_SINK=auto` registers iff OTel SDK importable AND `OTEL_EXPORTER_*` env present.

## 2. Sink implementations

- [x] 2.1 New package `src/a2kit/packages/ldd/sinks/__init__.py` re-exporting the four built-in sinks.
- [x] 2.2 `sinks/stderr_pretty.py` — `stderr_pretty_sink(emission)`; level-aware formatting; optional ANSI when stderr `isatty()`.
- [x] 2.3 `sinks/stderr_json.py` — `stderr_json_sink(emission)`; one JSON-line per accepted emission.
- [x] 2.4 `sinks/otel.py` — port a2web's `events/sinks.py` near-verbatim; rename logger to `a2kit.ldd.otel`; preserve the drain-on-missing-SDK behaviour.
- [x] 2.5 `sinks/live.py` — port a2web's `LiveSink` from `bench-live-sink-v1`; generalise event-name filter to `event_prefixes` tuple (default `("",)`); preserve asyncio.Lock; configurable heartbeat seconds.

## 3. Fan-out semantics

- [x] 3.1 Modify the LDD primitive(s) so that after the threshold filter passes, operator-sink dispatch and wire-sink dispatch run in parallel via `asyncio.gather(*..., return_exceptions=True)`.
- [x] 3.2 Log every exception result at WARN under `a2kit.ldd.sink_failed` with sink name + emission name + level; drop the exception.
- [x] 3.3 Verify that no producer is awaited on sink completion when sinks are async — fan-out runs in a background task per emission so producer rate is bounded by the threshold only.

## 4. Config wiring

- [x] 4.1 Extend `LddConfig` with `stderr_sink: Literal["none", "pretty", "json"] = "none"`, `otel_sink: Literal["auto", "on", "off"] = "auto"`, `live_sink: Literal["off", "on"] = "off"`, `live_heartbeat_seconds: float = 30.0`, `live_event_prefixes: tuple[str, ...] = ("",)`.
- [x] 4.2 Env mapping under existing `A2KIT_LDD__` prefix.
- [x] 4.3 App boot reads `LddConfig` and registers each enabled built-in sink BEFORE any user-added sinks. User-added sinks run after built-ins (order is documented as registration order).

## 5. Spec updates

- [x] 5.1 Land `ldd-operator-sinks` capability spec (this change's `specs/ldd-operator-sinks/spec.md`).
- [x] 5.2 Land `ldd-level-threshold` modification (clarifies threshold runs once, before both channels).
- [x] 5.3 Land `otel-adapter` modification (OTel sink is framework default opt-in; drain-on-missing invariant).

## 6. Docs

- [x] 6.1 New `docs/patterns/operator-and-wire-sinks.md` — short narrative covering the two channels and when consumers care.
- [x] 6.2 Update any existing LDD prose to use "emission channel" / "operator sink" / "wire sink".
- [x] 6.3 `CHANGELOG.md` under `[Unreleased]` — short entry; flag that default behaviour is unchanged.

## 7. a2web follow-up note (not in this change)

- [x] 7.1 In `BACKLOG.md`, add an entry: "Migrate a2web `src/a2web/events/sinks.py` → `app.ldd.add_otel()` (or env-driven auto). Trigger: after `reshape-ldd-operator-wire-fanout` lands in a2kit." (Logged so the consumer-side cleanup doesn't get forgotten.)

## 8. Verification

- [x] 8.1 `make test` green.
- [x] 8.2 With `A2KIT_LDD__STDERR_SINK=pretty` set, a tool emission produces a human-readable stderr line; with `=json`, a JSON record.
- [x] 8.3 With OTel SDK installed + `OTEL_EXPORTER_OTLP_ENDPOINT=...`, spans appear at the configured endpoint for every `*Ended` event.
- [x] 8.4 With `A2KIT_LDD__LIVE_SINK=on`, a long-running tool produces one-line-per-event output plus a heartbeat.
- [x] 8.5 Existing consumers with no env changes see identical behaviour (default config is the null change).
