## 0. Gate — RESOLVED

- [x] 0.1 Async-wire-boundary decision (2026-05-29): **live streaming is
      mandatory.** The MCP wire emission stays an inline `await
      ctx.log()` in the async primitive — never deferred behind a sync
      stdlib Handler, buffer, or end-of-call flush. No queue (inline
      await is simpler and lower-latency). Recorded in `design.md` and
      ADR 0027. Drives §4.2.

## 1. BDD specs (write tests first — per `feedback_bdd_first`)

- [ ] 1.1 `tests/capabilities/ldd_emission_surface/test_event_sugar_over_logging.py` — `event(TypedDataclass)` produces one stdlib `LogRecord` carrying the dumped payload in `extra`; enum values unwrapped.
- [ ] 1.2 `tests/capabilities/ldd_emission_surface/test_report_removed.py` — importing `report` / `reports` / `EventRegistry` from `a2kit.ldd` raises `ImportError` (removed-surface contract).
- [ ] 1.3 `tests/capabilities/ldd_emission_surface/test_loose_log_shorthands.py` — `info/debug/warning/error` route through the stdlib logger at the right level with fields.
- [ ] 1.4 `tests/capabilities/ldd_call_journal/test_call_id_per_dispatch.py` — each dispatch mints a unique `call_id` on the request scope; concurrent calls don't collide.
- [ ] 1.5 `tests/capabilities/ldd_call_journal/test_auto_capture_boundary.py` — the dispatch stage records args+result+timing+principal for a tool that emits nothing itself.
- [ ] 1.6 `tests/capabilities/ldd_call_journal/test_journal_jsonl_and_blob_sidecar.py` — a large body is content-addressed to a sidecar; the jsonl row carries the hash, not the body; row round-trips `json.loads`.
- [ ] 1.7 `tests/capabilities/ldd_call_journal/test_consumer_enrichment_same_call_id.py` — `journal_attach(...)` adds fields to the record under the active `call_id`.
- [ ] 1.8 `tests/capabilities/ldd_call_journal/test_domain_filter_scan.py` — given N journal rows across domains, a domain filter selects the right subset without reading blob sidecars.
- [ ] 1.9 `tests/capabilities/ldd_emission_surface/test_wire_streams_inline.py` — an `event()` mid-tool-body produces a wire log notification BEFORE the tool returns (assert via an in-process ctx stub that records emit timestamps relative to tool completion). Guards the no-regression-of-streaming invariant.

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

## 6. Config

- [ ] 6.1 Extend `LddConfig`: `journal_sink: Literal["off","on"] = "off"`, `journal_dir: str`, body-inlining threshold for content-addressing. Env under `A2KIT_LDD__`.
- [ ] 6.2 App boot registers the journal handler when enabled, alongside existing handlers; document registration order.

## 7. Docs + decision records

- [ ] 7.1 Land ADR 0027 (refound-ldd-on-stdlib-logging) — incl. the structlog rejection with both rationales (cold-start + code-size-illusion) and the resolved 0.1 branch. Run `make adr-index`.
- [ ] 7.2 Spec deltas: `ldd-emission-surface` (new), `ldd-call-journal` (new), `ldd-operator-sinks` (modified), `ldd-level-threshold` (modified).
- [ ] 7.3 `CHANGELOG.md` `[Unreleased]` — BREAKING: `report`/`@reports`/`EventRegistry` removed; `event()` preserved; journal added.
- [ ] 7.4 Update `docs/patterns/` LDD prose to the stdlib-logging framing.
- [ ] 7.5 `BACKLOG.md` — tick the "LDD reshape (Path A)" entry as executed; add the a2web follow-up (adopt `event()` unchanged, add `journal_attach`, delete hand-rolled `fetch_result.json` writers).

## 8. Verification

- [ ] 8.1 `openspec validate --changes --strict` green.
- [ ] 8.2 `make test` green.
- [ ] 8.3 Cold-start guard: `import a2kit` still does not import `fastapi`/`fastmcp` AND does not import structlog; emission path adds no measurable import cost over stdlib `logging`.
- [ ] 8.4 With `A2KIT_LDD__JOURNAL_SINK=on`, an a2web-style call writes a jsonl row + blob sidecars; a DuckDB query filters by `domain` without touching sidecars.
- [ ] 8.5 a2web's 26 `event()` sites compile and pass unchanged against the new surface.
