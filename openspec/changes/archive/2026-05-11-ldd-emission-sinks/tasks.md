## 0. Prerequisites

- [x] 0.1 Baseline: 684 tests passing, `make lint` clean, `ty check` clean (verified at end of router-as-plugin-with-surfaces phase).
- [x] 0.2 Baseline LDD test count: 12 (in `tests/test_ldd.py` + `tests/test_event_registry.py`; the `packages/ldd/` location is empty).
- [x] 0.3 Mirror discipline active — A2K-TEST-MIRROR firing 0 findings.

## 1. Spike — cancellation flush

- [x] 1.1 Stub body in `tests/test_spike_cancellation_flush.py` emits 20 events at 0.05s intervals (compressed from 30s to keep the test fast).
- [x] 1.2 CLI path verified — `redirect_stderr` captures the emitted lines under `anyio.fail_after`.
- [x] 1.3 Stderr lines counted; ≥3 of the expected 6 emissions land before timeout. Pass.
- [x] 1.4 MCP path: `ctx.log` is similarly synchronous-to-queue per FastMCP; same expected behavior. Sink fan-out (planned) is the only path with genuine mid-await risk — analyzed in spike doc.
- [x] 1.5 Findings captured as `docs/SPIKE_LDD_CANCELLATION.md`.
- [x] 1.6 **Decision: NO shielded scope.** a2web's feedback Q5 tolerates loss ("ok if we will send like 10 messages out of 20"). Emission is best-effort during cancellation. Documented in spike doc + Q6.

## 2. `LddEmission` + `LddSink` protocol

- [x] 2.1 `LddEmission` frozen+slots dataclass added to `src/a2kit/packages/ldd/__init__.py` with fields per D-EMISSION-SHAPE.
- [x] 2.2 `LddSink` Protocol added (single async `__call__`).
- [x] 2.3 Re-exported via `a2kit.ldd` (`src/a2kit/ldd.py`).
- [x] 2.4 `tests/test_ldd_sinks.py` covers frozen-ness, field round-trip, structural typing implicitly (passing functions where LddSink is expected).

## 3. `_LddState` carries sinks

- [x] 3.1 `_LddState` carries `sinks: tuple[LddSink, ...] = ()`.
- [x] 3.2 `ldd_state_for_call` accepts `sinks=` kwarg, default `()` — preserves existing call sites.
- [x] 3.3 `test_state_resets_after_context_exit` in `tests/test_ldd_sinks.py` covers the reset behavior.

## 4. Fan-out in `event()` / `report()`

- [x] 4.1 `event()` fans out to `state.sinks` after the wire emit via `_dispatch_sinks` helper (error-isolation per D-ERROR-ISOLATION).
- [x] 4.2 `report()` does the same; emission built once with the validated payload.
- [x] 4.3 No shield (per spike decision §1.6).
- [x] 4.4 `tests/test_ldd_sinks.py` — 11 tests cover event + report fan-out, registration order, exception isolation, kill-switch, state reset.

## 5. `_AppLdd` grows `add_sink` / `remove_sink` / `sinks`

- [x] 5.1 `_AppLdd.__slots__` carries `_sinks` (and `events`); `__init__` initializes both.
- [x] 5.2 `add_sink`, `remove_sink`, `sinks` (property returns tuple) added. `remove_sink` of unregistered raises ValueError (stdlib list.remove behavior).
- [x] 5.3 `tests/test_ldd_sinks.py` covers add/remove round-trip and tuple immutability.

## 6. Dispatch sites pass sinks into state

- [x] 6.1 `invoke_tool_sync` reads `app.ldd.sinks` and threads through `_invoke_tool_in_process` into `ldd_state_for_call`.
- [x] 6.2 `build_mcp_server` snapshots `app.ldd.sinks` and passes to each tool's `_wrap_with_ldd_state`.
- [x] 6.3 `test_in_process_client_propagates_sinks_to_dispatch` in `tests/test_ldd_sinks.py` verifies end-to-end through the testing client.

## 7. Documentation — `OPERATIONAL_CONTRACTS.md` Q6

- [x] 7.1 Q6 rewritten with three sub-sections: heartbeat events, add_sink API, cancellation contract.
- [x] 7.2 Heartbeat pattern documented with worked example (typed event + task-group + interval emit).
- [x] 7.3 `add_sink` documented with OTel sink example covering attribute mapping.
- [x] 7.4 Cancellation contract documented: completed emits land everywhere; in-flight may drop; sinks should be synchronous-fast.
- [x] 7.5 Spike doc cross-linked.

## 8. Quality gates

- [x] 8.1 `uv run pytest -q --no-cov` — 696 passed (was 684 baseline; +12 sink tests including spike).
- [x] 8.2 `make lint` — 0 findings.
- [x] 8.3 `uv run ty check src/` — clean.
- [x] 8.4 Cold-start: 7.9ms (well under budget; smaller than v0.25 baseline due to import-graph improvements during phase 7).
- [x] 8.5 `openspec validate ldd-emission-sinks --strict` — green.
