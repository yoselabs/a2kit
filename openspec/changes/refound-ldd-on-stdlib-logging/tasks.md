## 0. Gate — RESOLVED

- [x] 0.1 Async-wire-boundary decision (2026-05-29): **live streaming is
      mandatory.** The MCP wire emission stays an inline `await
      ctx.log()` in the async primitive — never deferred behind a sync
      stdlib Handler, buffer, or end-of-call flush. No queue (inline
      await is simpler and lower-latency). Recorded in `design.md` and
      ADR 0027. Drives §4.2.
- [x] 0.2 Concept decision (2026-05-30): the durable record is an
      **access-log** (one author concept `a2kit.log`; the call record is
      a dedicated `a2kit.calls` logger + opt-in file handler), NOT a
      second `a2kit.journal` namespace and NOT a `record()` enrichment
      verb. Enrichment is `debug` logging correlated by `call_id`.
      Recorded in `design.md` + ADR 0027. Drives §1.7, §5, §5b.

## Code map (verified 2026-06-03 — paths the tasks below target)

The package lives under `src/a2kit/`, NOT root `packages/` (root `packages/`
holds only `a2effect`). Concrete targets:

- `src/a2kit/packages/ldd/` — `ambient.py` (`_LddState`, `_require_ambient_state`),
  `emission.py` (`debug`/`info`/`warning`/`error`/`event`/`log`/`report`),
  `levels.py` (`LddLevel`, `LDD_LEVEL_RANK`), `wire.py` (re-exports `_ldd_wire`),
  `sinks/` (`stderr_pretty`/`stderr_json`/`otel`/`live`/`_core`), `__init__.py`.
- `src/a2kit/ldd.py` — **public alias module** (`a2kit.ldd`); renames to `src/a2kit/log.py`.
- `src/a2kit/_ldd_wire.py` — `TEXT_CAP`/`format_ldd_line` (runtime layer, hoisted
  above the package on purpose to dodge the layer cycle). Renames to `_log_wire.py`.
- `src/a2kit/_ldd_bootstrap.py` — `register_builtin_ldd_sinks(app_ldd, ldd_config)`;
  **the file §6.2 edits** to also register the `a2kit.calls` logger. Renames to `_log_bootstrap.py`.
- `src/a2kit/config.py:66` — `class LddConfig` (in-file rename → `LogConfig`, §6.1).
- `src/a2kit/packages/dispatch/stages.py` — `LddStateStage` (line ~221, the dispatch
  site that mints state, §2.5); the new `CallLogStage` (§5.1) joins this module.
- `src/a2kit/packages/lint/rules/ldd.py` — the lint rule to prune (§3.3).
- Callers of `ldd_state_for_call` to update (§5b.3): `dispatch/stages.py`,
  `packages/testing/fixtures.py`, `exceptions.py` (docstring refs `_LddState`).
- Test files/dirs the rename (§5b) must move: `tests/ldd/`, `tests/packages/ldd/`,
  `tests/capabilities/ldd_operator_sinks/` (→ `log_handlers/`), `tests/test_ldd.py`,
  `tests/test__ldd_wire.py`, `tests/test__ldd_bootstrap.py`, `tests/config/test_ldd_config.py`,
  `tests/capabilities/request_scope/test_ldd_state_via_scope.py`,
  `tests/capabilities/thin_core_surface/test_lazy_ldd_emission_top_level.py`.
  Surface snapshot: `tests/surface/expected_tier_ldd.txt` (§5b.6).

## 1. BDD specs (write tests first — per `feedback_bdd_first`)

- [x] 1.1 `tests/capabilities/log_emission_surface/test_level_method_accepts_instance.py` — `info(TypedDataclass)` produces one stdlib `LogRecord` carrying the dumped payload in `extra`; enum values unwrapped. (instance-as-payload under the level method; no `event()` verb.)
- [x] 1.2 `tests/capabilities/log_emission_surface/test_removed_surface.py` — importing `report` / `reports` / `EventRegistry` / `event` / `log` (the loose verb) from `a2kit.log` (or old `a2kit.ldd`) raises `ImportError`; there is no `a2kit.journal` module.
- [x] 1.3 `tests/capabilities/log_emission_surface/test_level_methods.py` — `info/debug/warning/error` route through the stdlib logger at the right level with fields.
- [x] 1.4 `tests/capabilities/call_log/test_call_id_per_dispatch.py` — each dispatch mints a unique `call_id`; concurrent `gather`-interleaved calls stay isolated (A→A, B→B); a child task inherits the parent `call_id`. (Guards the verified-isolation property `feedback_parallel_runs` depends on.)
- [x] 1.5 `tests/capabilities/call_log/test_auto_capture_boundary.py` — the dispatch-boundary stage records args+result+timing+principal for a tool that emits nothing; result is the RAW pre-formatter value; the record is emitted on the `a2kit.calls` logger.
- [x] 1.6 `tests/capabilities/call_log/test_jsonl_and_blob_sidecar.py` — a large body is content-addressed to a sidecar; the jsonl row carries the hash; row round-trips `json.loads`; a newline-bearing value stays on one physical line.
- [x] 1.7 `tests/capabilities/call_log/test_enrichment_is_debug_logging.py` — `a2kit.log.debug("html", html=h)` during dispatch lands in the call-log file (CALL_LOG_LEVEL=DEBUG), carries the active `call_id`, and is queryable alongside the auto-record by grouping on `call_id`. (Enrichment = debug logging correlated by call_id; NO `record()` verb.)
- [x] 1.8 `tests/capabilities/call_log/test_call_records_never_stream.py` — **the topology guarantee.** The `a2kit.calls` logger has `propagate=False` and the wire + stdout handlers are NOT attached to it; an auto call-record (and a `debug` blob) never appears on the MCP wire or stdout, even with `WIRE_LEVEL=DEBUG`.
- [x] 1.9 `tests/capabilities/call_log/test_domain_filter_scan.py` — a DuckDB-style domain filter selects rows without reading blob sidecars.
- [x] 1.10 `tests/capabilities/log_emission_surface/test_wire_streams_inline.py` — `info(...)` mid-tool-body produces a wire notification BEFORE the tool returns. Guards no-regression-of-streaming.
- [x] 1.11 `tests/capabilities/call_log/test_identical_fields_across_interfaces.py` — same call via CLI and via MCP yields identical captured fields (the relaxed invariant).
- [x] 1.12 `tests/capabilities/call_log/test_span_shape_and_nesting.py` — record carries `trace_id`/`span_id`/`parent_span_id`; a nested tool call sets `parent_span_id` to the outer `span_id`.
- [x] 1.13 `tests/capabilities/call_log/test_error_and_streaming_capture.py` — an erroring tool captures the typed error in the result position; a generator return captures the materialized value, never a bare generator object.
- [x] 1.14 `tests/capabilities/call_log/test_opt_in_off_by_default.py` — with `CALL_LOG=off` (default) no file is written and the boundary stage self-skips; `CALL_LOG=on` writes it.

## 2. Re-found emission on stdlib logging

- [x] 2.1 Replace `_LddState` ambient with a `logging.Filter` that reads the request-scope contextvar and injects `call_id`, `tool_name`, `elapsed_ms` onto each record.
- [x] 2.2 Fold `levels.py` ranks → stdlib logging levels; keep the `trace` *level* alias mapping.
- [x] 2.3 Fold `wire.py` / `TEXT_CAP` / `format_ldd_line` → a `logging.Formatter` (the condensed `[ +s.mmm LEVEL] msg key=val` line; byte-stable) for the LLM-facing handlers.
- [x] 2.4 Reduce `emission.py` to the level-method wrappers (`debug`/`info`/`warning`/`error`), each accepting a message+fields OR a typed instance (instance → logger call with `extra=payload`). NO `event()` verb, NO loose `log()` verb.
- [x] 2.5 Mint `call_id` per dispatch in the dispatch site (`LddStateStage`, `src/a2kit/packages/dispatch/stages.py`), alongside the existing LDD state setup.

## 3. Delete dead surface

- [x] 3.1 Remove `report()`, `@reports(T)`, `report_type` on state, `ReportTypeNotDeclared`, `ReportTypeMismatch`.
- [x] 3.2 Remove `EventRegistry`, `events.register`, `emit_typed`, the progress-callback path, and `_AppLdd` report members.
- [x] 3.3 Delete the now-orphaned parts of `src/a2kit/packages/lint/rules/ldd.py`; keep only any rule that still polices a live invariant (likely none).
- [x] 3.4 Confirm the layer-cycle workarounds (`_ldd_wire` below L0, `ambient → request_scope # noqa: A2K-LAYER`) can be removed; remove them if the stdlib refounding dissolves the cycle.

## 4. Sinks → handlers (incl. per-handler levels + the wire async boundary, branch from 0.1)

- [x] 4.1 Re-express `otel_sink` / `live_sink` / `stderr_pretty` / `stderr_json` as sync `logging.Handler`s on the `a2kit` logger; preserve behaviour and the failure-isolation contract (a failing handler never aborts siblings, the wire, or the producer).
- [x] 4.2 Wire emission stays an inline `await ctx.log()` in the async level-method primitive — NOT routed through a sync stdlib Handler, NOT buffered, NOT queued. This is the streaming-no-regression requirement; the async primitives keep their current shape.
- [x] 4.3 Per-handler levels: wire + stderr default `INFO+` (so `debug` does not stream); `live_sink` stays a sync stdout handler (operator feed). The call-log file handler is `DEBUG+` (§5) and lives on a different logger.

## 5. Call access-log (new capability)

- [x] 5.1 New `DISPATCH_PIPELINE` stage (`CallLogStage`): auto-capture args+result+timing+principal at the boundary, keyed by `call_id`; emit the finalized record on the dedicated `a2kit.calls` logger. Capture the RAW return value before the formatter. Define error (typed-error in result position) and streaming (materialized value, never bare generator) capture.
- [x] 5.2 Dedicated logger `a2kit.calls` with `propagate=False`; ONLY the call-log file handler is attached. The wire/stderr handlers are on `a2kit` and NOT attached to `a2kit.calls` — the structural guarantee that call records (and `debug` blobs routed to the file) can never stream to the agent or stdout. (Backs test 1.8.)
- [x] 5.3 Call-log **file handler** (`logging.Handler`): JSONL-per-day rows + content-addressed blob sidecars (`hash → bodies/<hash>`) above a size threshold; columns `call_id, ts, tool, domain, principal, elapsed_ms, trace_id, span_id, parent_span_id, *_hash`. JSON-escaped values stay one line. Sync (file write = "write now").
- [x] 5.4 Derive `domain` from the URL arg where present (a2web's case); leave null otherwise.
- [x] 5.5 Mint `call_id` as a standalone request-scope primitive readable by any stage even when the call-log is off (shared spine for future gate stages, e.g. a2ledger). Settle the thin-record-vs-rich-contract placement (design.md OPEN) when building the record schema; default lean is thin record + open `extra` bag.
- [x] 5.6 `CallRecord` is span-shaped: `trace_id` / `span_id` / `parent_span_id` alongside `call_id`, NO OTel SDK import. `parent_span_id` set from the enclosing call's `span_id` for nested dispatch. Shape convertible to OTLP so the `otel` handler can export it.
- [x] 5.7 Enrichment is `debug` logging, NOT a verb: domain blobs the boundary can't see (`raw_html`, `extracted_md`) are logged via `a2kit.log.debug("html", html=h)`, captured by the file handler (CALL_LOG_LEVEL=DEBUG), correlated to the auto-record by `call_id`. NO `journal.record(...)`, NO merged-record API — DuckDB groups by `call_id`. Document the out-of-dispatch eval-metadata case (computed with no active call scope → consumer correlates by an explicit `call_id` it carries, not auto-capture).
- [x] 5.8 Auto-capture is call-I/O ONLY (args/result/timing/principal). Harness/consumer metadata (cost, cache-hit, model) is `debug`-logged enrichment correlated by `call_id`, not auto-capture. Document the contextvar-does-not-cross-thread edge.

## 5b. Rename — retire "LDD", one surface `a2kit.log` (no backward-compat alias)

- [x] 5b.1 Rename package `src/a2kit/packages/ldd/` → `src/a2kit/packages/log/`; public alias module `src/a2kit/ldd.py` → `src/a2kit/log.py`; runtime helpers `src/a2kit/_ldd_wire.py` → `_log_wire.py` and `src/a2kit/_ldd_bootstrap.py` → `_log_bootstrap.py`. `a2kit.ldd` → `a2kit.log` (THE author surface: `debug`/`info`/`warning`/`error`, each taking a message OR a typed instance). NO `a2kit.ldd` alias, NO shim, NO `event()`/`log()` verb.
- [x] 5b.2 NO `a2kit.journal` public module. The call-log is internal: the `a2kit.calls` logger (§5.2), `CallLogStage` (§5.1), and the file handler (§5.3). The author never imports it; it is configured, not called.
- [x] 5b.3 `_LddState` → `_CallScope` `{call_id, ctx, start_monotonic, record}` (per-runtime fields removed per §2/§3); `ldd_state_for_call` → `bind_call_scope` (dispatcher SPI; update CLI/MCP/test callers). `_CallScope` stays neutral — NOT `_LogScope` (it is the shared spine for both the app log and the access record).
- [x] 5b.4 `LddConfig` → `LogConfig`; env `A2KIT_LDD__*` → `A2KIT_LOG__*`; `app.ldd` → `app.log`. No `app.journal`.
- [x] 5b.5 Wire keys: keep `a2kit_*` prefix (kind/name/payload/elapsed_ms) but re-baseline the byte-equality tests; no `ldd` token in any payload.
- [x] 5b.6 Tier-2 snapshot gate: replace `tests/surface/expected_tier_ldd.txt` with `expected_tier_log.txt` (the SOLE public surface — there is no separate journal surface to snapshot); update `TIER2_MODULES` in `tests/surface/test_tier2_surfaces.py`.
- [x] 5b.7 Capability spec dirs/names: `ldd-emission-surface` → `log-emission-surface`, `ldd-call-journal` → `call-log`, `ldd-operator-sinks` → `log-handlers`, `ldd-level-threshold` → folded into stdlib levels (retire as bespoke spec).

## 6. Config

- [x] 6.1 `LogConfig` (renamed from `LddConfig`): add `call_log: Literal["off","on"] | str = "off"` (a str is a path), `call_log_level: Literal["DEBUG","INFO"] = "DEBUG"`, `wire_level: str = "INFO"`, `call_log_dir: str`, body-inlining threshold for content-addressing. Env under `A2KIT_LOG__`.
- [x] 6.2 App boot (`src/a2kit/_ldd_bootstrap.py` → `_log_bootstrap.py`, `register_builtin_ldd_sinks`) wires the `a2kit` logger (stderr/wire/live handlers, INFO+) and — when `call_log` is on — the `a2kit.calls` logger (`propagate=False`) + the call-log file handler (DEBUG+/INFO+ per `call_log_level`); document registration order and the `propagate=False` invariant.

## 7. Docs + decision records

- [x] 7.1 Land ADR 0027 (refound-ldd-on-stdlib-logging) — incl. the structlog rejection (cold-start + code-size-illusion), the resolved 0.1 wire branch, and the 0.2 access-log concept decision. Run `make adr-index`.
- [x] 7.2 Spec deltas under the renamed capabilities: `log-emission-surface` (new), `call-log` (new), `log-handlers` (modified from `ldd-operator-sinks`); retire `ldd-level-threshold` (folded into stdlib levels). The change-dir spec folders are renamed to match before archive.
- [x] 7.3 `CHANGELOG.md` `[Unreleased]` — BREAKING: `a2kit.ldd` → `a2kit.log` (no `a2kit.journal`); `LddConfig`→`LogConfig`; `A2KIT_LDD__*`→`A2KIT_LOG__*`; `report`/`@reports`/`EventRegistry`/`event` removed. Migration table maps every old name → new (no aliases).
- [x] 7.4 Update `docs/patterns/` + every docstring (incl. `src/a2kit/packages/ldd/__init__.py:1` "Logging / Data / Diagnostics") to the log + call-access-log framing; zero "LDD" left in src prose.
- [x] 7.5 `BACKLOG.md` — tick the "LDD reshape (Path A)" entry as executed; add the a2web follow-up (migrate to `a2kit.log.info`, log bodies at `debug`, turn on the call-log, delete hand-rolled `fetch_result.json` writers).
- [x] 7.6 ADR 0004 amendment note: the tier-2 surface `a2kit.ldd` is replaced by `a2kit.log` (snapshot regen, recorded by this change). ADR 0027 supersedes the reshape change's "keep ldd for stability" concession.

## 8. Verification

- [x] 8.1 `openspec validate --changes --strict` green.
- [x] 8.2 `make test` green.
- [x] 8.3 Cold-start guard: `import a2kit` still does not import `fastapi`/`fastmcp` AND does not import structlog; emission path adds no measurable import cost over stdlib `logging`.
- [x] 8.4 With `A2KIT_LOG__CALL_LOG=on`, an a2web-style call writes a jsonl row + blob sidecars; a DuckDB query filters by `domain` without touching sidecars; the same call produces NOTHING extra on the wire/stdout (topology guarantee).
- [x] 8.6 No-redundancy guard: `grep -ri "\bldd\b" src/` returns zero hits outside historical ADR/CHANGELOG entries; no `a2kit.ldd` and no `a2kit.journal` import path resolves.
