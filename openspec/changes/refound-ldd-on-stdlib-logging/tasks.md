## 0. Gate — RESOLVED

- [x] 0.1 Async-wire-boundary decision (2026-05-29): **live streaming is
      mandatory.** The MCP wire emission stays an inline `await
      ctx.log()` in the async primitive — never deferred behind a sync
      stdlib Handler, buffer, or end-of-call flush. No queue (inline
      await is simpler and lower-latency). Recorded in `design.md` and
      ADR 0027. Drives §4.2.

## 1. BDD specs (write tests first — per `feedback_bdd_first`)

- [ ] 1.1 `tests/capabilities/trace_emission_surface/test_level_method_accepts_instance.py` — `info(TypedDataclass)` produces one stdlib `LogRecord` carrying the dumped payload in `extra`; enum values unwrapped. (instance-as-payload under the level method; no `event()` verb.)
- [ ] 1.2 `tests/capabilities/trace_emission_surface/test_removed_surface.py` — importing `report` / `reports` / `EventRegistry` / `event` from `a2kit.trace` (or old `a2kit.ldd`) raises `ImportError`.
- [ ] 1.3 `tests/capabilities/trace_emission_surface/test_level_methods.py` — `info/debug/warning/error` route through the stdlib logger at the right level with fields.
- [ ] 1.4 `tests/capabilities/call_journal/test_call_id_per_dispatch.py` — each dispatch mints a unique `call_id`; concurrent `gather`-interleaved calls stay isolated (A→A, B→B); a child task inherits the parent `call_id`. (Guards the verified-isolation property `feedback_parallel_runs` depends on.)
- [ ] 1.5 `tests/capabilities/call_journal/test_auto_capture_boundary.py` — the neutral dispatch stage records args+result+timing+principal for a tool that emits nothing; result is the RAW pre-formatter value.
- [ ] 1.6 `tests/capabilities/call_journal/test_journal_jsonl_and_blob_sidecar.py` — a large body is content-addressed to a sidecar; the jsonl row carries the hash; row round-trips `json.loads`.
- [ ] 1.7 `tests/capabilities/call_journal/test_enrichment_same_call_id.py` — `a2kit.journal.attach(...)` adds fields under the active `call_id`; two enrichers merge without clobber.
- [ ] 1.8 `tests/capabilities/call_journal/test_domain_filter_scan.py` — a domain filter selects rows without reading blob sidecars.
- [ ] 1.9 `tests/capabilities/trace_emission_surface/test_wire_streams_inline.py` — `info(...)` mid-tool-body produces a wire notification BEFORE the tool returns. Guards no-regression-of-streaming.
- [ ] 1.10 `tests/capabilities/call_journal/test_identical_fields_across_interfaces.py` — same call via CLI and via MCP yields identical captured fields (the relaxed invariant).
- [ ] 1.11 `tests/capabilities/call_journal/test_span_shape_and_nesting.py` — record carries `trace_id`/`span_id`/`parent_span_id`; a nested tool call sets `parent_span_id` to the outer `span_id`.
- [ ] 1.12 `tests/capabilities/call_journal/test_error_and_streaming_capture.py` — an erroring tool captures the typed error in the result position; a generator return captures the materialized value, never a bare generator object.

## 2. Re-found emission on stdlib logging

- [ ] 2.1 Replace `_LddState` ambient with a `logging.Filter` that reads the request-scope contextvar and injects `call_id`, `tool_name`, `elapsed_ms` onto each record.
- [ ] 2.2 Fold `levels.py` ranks → stdlib logging levels; keep the `trace` alias mapping.
- [ ] 2.3 Fold `wire.py` / `TEXT_CAP` / `format_ldd_line` → a `logging.Formatter` (the condensed `[ +s.mmm LEVEL] msg key=val` line; byte-stable).
- [ ] 2.4 Reduce `emission.py` to the `event()` sugar (logger call + `extra=payload`) + the loose `info/debug/warning/error` wrappers.
- [ ] 2.5 Mint `call_id` per dispatch in the dispatch site (alongside the existing LDD state setup).

## 3. Delete dead surface

- [ ] 3.1 Remove `report()`, `@reports(T)`, `report_type` on state, `ReportTypeNotDeclared`, `ReportTypeMismatch`.
- [ ] 3.2 Remove `EventRegistry`, `events.register`, `emit_typed`, the progress-callback path, and `_AppLdd` report members.
- [ ] 3.3 Delete the now-orphaned parts of `packages/lint/rules/ldd.py`; keep only any rule that still polices a live invariant (likely none).
- [ ] 3.4 Confirm the layer-cycle workarounds (`_ldd_wire` below L0, `ambient → request_scope # noqa: A2K-LAYER`) can be removed; remove them if the stdlib refounding dissolves the cycle.

## 4. Sinks → handlers (incl. the wire async boundary, branch from 0.1)

- [ ] 4.1 Re-express `otel_sink` / `live_sink` / `stderr_pretty` / `stderr_json` / journal as sync `logging.Handler`s; preserve behaviour and the failure-isolation contract (a failing handler never aborts siblings, the wire, or the producer).
- [ ] 4.2 Wire emission stays an inline `await ctx.log()` in the async `event()` / `log()` primitive — NOT routed through a sync stdlib Handler, NOT buffered, NOT queued. This is the streaming-no-regression requirement; the async primitives keep their current shape.
- [ ] 4.3 `live_sink` stays a sync stdout handler (operator terminal feed). CLI/serve sync handlers fire synchronously (already real-time); only the wire needs the async-inline path.

## 5. Journal handler (new capability)

- [ ] 5.1 `sinks/journal.py` — full-fidelity handler: jsonl-per-day rows + content-addressed blob sidecars (`hash → bodies/<hash>`); columns `call_id, ts, tool, domain, principal, elapsed_ms, *_hash`.
- [ ] 5.2 New `DISPATCH_PIPELINE` stage: auto-capture args+result+timing+principal at the boundary, keyed by `call_id`.
- [ ] 5.3 `journal_attach(**fields)` consumer-enrichment primitive: merge fields into the active-`call_id` record (ADR 0022 consumer-owned payload).
- [ ] 5.4 Derive `domain` from the URL arg where present (a2web's case); leave null otherwise.
- [ ] 5.5 Mint `call_id` as a standalone request-scope primitive readable by any stage even when the journal is off (shared spine for future gate stages, e.g. a2ledger). Settle the thin-record-vs-rich-contract placement (design.md OPEN) when building the record schema; default lean is thin record + open `extra` bag.
- [ ] 5.6 `CallRecord` is span-shaped: `trace_id` / `span_id` / `parent_span_id` alongside `call_id`, NO OTel SDK import. `parent_span_id` set from the enclosing call's `span_id` for nested dispatch. Shape convertible to OTLP so `otel` handler can export it.
- [ ] 5.7 The journal is a transport-NEUTRAL `DISPATCH_PIPELINE` stage, NOT a `logging.Handler`. Capture the RAW return value before the formatter. Define error (typed-error in result position) and streaming (materialized value, never bare generator) capture.
- [ ] 5.8 Auto-capture is call-I/O ONLY (args/result/timing/principal). Harness/consumer metadata (cost, cache-hit, model) is enrichment under `call_id`, not auto-capture. Document the contextvar-does-not-cross-thread edge.

## 5b. Rename — retire "LDD", split trace/journal (no backward-compat alias)

- [ ] 5b.1 Rename package `packages/ldd/` → `packages/trace/`; public module `a2kit.ldd` → `a2kit.trace` (emission: `event`/`log`/`info`/`debug`/`warning`/`error`). NO `a2kit.ldd` alias, NO shim.
- [ ] 5b.2 New public module `a2kit.journal` (durable record: `attach(**fields)` + `CallRecord`). The dispatch-boundary auto-capture (§5.2) and `journal_attach` (§5.3) live under this name; rename `journal_attach` → `journal.attach`.
- [ ] 5b.3 `_LddState` → `_CallScope` `{call_id, ctx, start_monotonic, record}` (per-runtime fields removed per §2/§3); `ldd_state_for_call` → `bind_call_scope` (dispatcher SPI; update CLI/MCP/test callers).
- [ ] 5b.4 `LddConfig` → `TraceConfig`; env `A2KIT_LDD__*` → `A2KIT_TRACE__*`; `app.ldd` → `app.trace` + new `app.journal`.
- [ ] 5b.5 Wire keys: keep `a2kit_*` prefix (kind/name/payload/elapsed_ms) but re-baseline the byte-equality tests; no `ldd` token in any payload.
- [ ] 5b.6 Tier-2 snapshot gate: replace `tests/surface/expected_tier_ldd.txt` with `expected_tier_trace.txt` + `expected_tier_journal.txt`; update `TIER2_MODULES` in `tests/surface/test_tier2_surfaces.py`.
- [ ] 5b.7 Capability spec dirs/names: `ldd-emission-surface` → `trace-emission-surface`, `ldd-call-journal` → `call-journal`, `ldd-operator-sinks` → `trace-handlers`, `ldd-level-threshold` → folded into stdlib levels (retire as bespoke spec).
- [ ] 5b.8 a2web lockstep: migrate 26 `a2kit.ldd.event(...)` → `a2kit.trace.event(...)`; add `a2kit.journal.attach(...)` enrichment; CHANGELOG migration table.

## 6. Config

- [ ] 6.1 `TraceConfig` (renamed from `LddConfig`): add `journal_sink: Literal["off","on"] = "off"`, `journal_dir: str`, body-inlining threshold for content-addressing. Env under `A2KIT_TRACE__`.
- [ ] 6.2 App boot registers the journal handler when enabled, alongside existing handlers; document registration order.

## 7. Docs + decision records

- [ ] 7.1 Land ADR 0027 (refound-ldd-on-stdlib-logging) — incl. the structlog rejection with both rationales (cold-start + code-size-illusion) and the resolved 0.1 branch. Run `make adr-index`.
- [ ] 7.2 Spec deltas under the renamed capabilities: `trace-emission-surface` (new), `call-journal` (new), `trace-handlers` (modified from `ldd-operator-sinks`); retire `ldd-level-threshold` (folded into stdlib levels). The change-dir spec folders are renamed to match before archive.
- [ ] 7.3 `CHANGELOG.md` `[Unreleased]` — BREAKING: `a2kit.ldd` → `a2kit.trace` + new `a2kit.journal`; `LddConfig`→`TraceConfig`; `A2KIT_LDD__*`→`A2KIT_TRACE__*`; `report`/`@reports`/`EventRegistry` removed. Migration table maps every old name → new (no aliases).
- [ ] 7.4 Update `docs/patterns/` + every docstring (incl. `packages/ldd/__init__.py:1` "Logging / Data / Diagnostics") to the trace/journal framing; zero "LDD" left in src prose.
- [ ] 7.5 `BACKLOG.md` — tick the "LDD reshape (Path A)" entry as executed; add the a2web follow-up (migrate to `a2kit.trace.event`, add `a2kit.journal.attach`, delete hand-rolled `fetch_result.json` writers).
- [ ] 7.6 ADR 0004 amendment note: the tier-2 surface `a2kit.ldd` is replaced by `a2kit.trace` + `a2kit.journal` (snapshot regen, recorded by this change). ADR 0027 supersedes the reshape change's "keep ldd for stability" concession.

## 8. Verification

- [ ] 8.1 `openspec validate --changes --strict` green.
- [ ] 8.2 `make test` green.
- [ ] 8.3 Cold-start guard: `import a2kit` still does not import `fastapi`/`fastmcp` AND does not import structlog; emission path adds no measurable import cost over stdlib `logging`.
- [ ] 8.4 With `A2KIT_TRACE__JOURNAL_SINK=on`, an a2web-style call writes a jsonl row + blob sidecars; a DuckDB query filters by `domain` without touching sidecars.
- [ ] 8.5 a2web migrates to `a2kit.trace.event(...)` + `a2kit.journal.attach(...)` and passes against the new surface.
- [ ] 8.6 No-redundancy guard: `grep -ri "\bldd\b" src/` returns zero hits outside historical ADR/CHANGELOG entries; no `a2kit.ldd` import path resolves.
