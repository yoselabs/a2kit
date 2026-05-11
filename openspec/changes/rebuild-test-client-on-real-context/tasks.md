# Tasks — rebuild the in-process test client on real fastmcp.Context

## 0. Prerequisites

- [ ] 0.1 Baseline: `make lint` green, `make test` green at HEAD
      (post `field-logging-via-ldd`). Record the test count
      (currently 728).
- [ ] 0.2 Smoke: write a throwaway test that does
      `async with fastmcp.Client(transport=build_mcp_server(app))`
      against a 3-tool app and observe (a) lifecycle hooks run,
      (b) ctx is `fastmcp.Context` not `StderrToolContext`,
      (c) `notifications/message` arrive via `log_handler`. Confirm
      the architectural assumption before refactoring.
- [ ] 0.3 Per design Open Question 1: probe how the in-memory
      transport propagates raised exceptions. Document the answer
      (`ToolError`-wrapped or transparent) in a comment in
      `client.py`.
- [ ] 0.4 Per design Open Question 3: probe `CancelledError`
      behaviour through the in-memory transport against the
      existing `test_spike_cancellation_flush` fixture.

## 1. Library — rewrite `src/a2kit/packages/testing/client.py`

- [ ] 1.1 Add the structured `LogLine` / `EventLine` / `ReportLine`
      named-tuples or frozen dataclasses (D-LOGS-SHAPE).
- [ ] 1.2 Rewrite `TestClient` per D-CLIENT-CTOR. Construct
      `build_mcp_server(self._app)` + `fastmcp.Client(transport=...,
      log_handler=..., progress_handler=...)`. Manage both via
      `__aenter__` / `__aexit__`.
- [ ] 1.3 Implement `_on_log` per D-LOG-HANDLER. Fan-out by
      `extra["a2kit_kind"]` into `events` / `reports` / `logs`.
- [ ] 1.4 Implement `_on_progress` per D-PROGRESS-HANDLER. Populate
      both `progress` (2-tuple) and `progress_with_message`
      (3-tuple).
- [ ] 1.5 Implement `invoke(tool_name, /, **kwargs)` per D-INVOKE.
- [ ] 1.6 Add `logs_text: list[str]` derived property that renders
      each captured `LogLine` via `format_ldd_line`.
- [ ] 1.7 Delete `_CapturingContext`. Confirm no other module in
      `src/` imports it.

## 2. Tests — migrate `tests/test_in_process_client.py`

- [ ] 2.1 Re-run the test file against the rewritten client; expect
      breakages where assertions read `c.logs[0]` as a string.
- [ ] 2.2 Migrate string-shape assertions to either structured
      (`c.logs[0].level == "info"`) or rendered (`"INFO" in
      c.logs_text[0]`). Prefer structured; document the choice with
      a one-line comment.
- [ ] 2.3 Verify `c.events`, `c.reports`, `c.progress` assertions
      pass unchanged.
- [ ] 2.4 Add a new scenario that asserts the lifecycle runs:
      `@app.on_startup` resolves; tool invocation sees the
      startup-provided singleton. This is a behavioural improvement
      worth pinning.

## 3. Tests — sweep other consumers

- [ ] 3.1 `grep -rn "c.logs\b\|client.logs\b" tests/` — find every
      consumer of the structured-shape change. Migrate each.
- [ ] 3.2 `tests/test_ldd_sinks.py` — sink fan-out should be
      unchanged; just verify.
- [ ] 3.3 `tests/test_typed_emit.py`, `tests/test_event_registry.py`
      — sweep for any `_CapturingContext` direct construction.
- [ ] 3.4 `tests/examples/*/test_server.py` — check whether any
      example test uses the in-process client directly. (Most use
      `CliRunner` + `build_full_cli`; unaffected.)

## 4. Spec edits

- [ ] 4.1 `openspec/changes/rebuild-test-client-on-real-context/specs/in-process-test-client/spec.md`
      — modify the existing "implementation backed by CLI subclass"
      requirement to "implementation backed by real FastMCP
      in-memory transport." Add scenarios for `(a)` ctx-is-real-
      fastmcp-Context, `(b)` lifecycle-runs-in-scope, `(c)`
      structured-logs-shape.

## 5. Documentation

- [ ] 5.1 README — "Testing tools" section: document the
      structured `logs` shape and the `logs_text` rendered property.
- [ ] 5.2 ANTIPATTERNS.md — entry pinning "Don't construct
      `StderrToolContext` directly in tests" if any test was doing
      this for the legacy capture pattern.
- [ ] 5.3 `tests/test_in_process_client.py` module docstring —
      note the real-transport backing so test authors understand
      this file is structurally a transport-level test, not a unit
      test.

## 6. Verification

- [ ] 6.1 `make lint` green.
- [ ] 6.2 `make test` green; test count matches baseline ± any
      scenarios intentionally added in 2.4.
- [ ] 6.3 `tests/test_field_logging_mcp_path.py` (the original repro
      suite from `field-logging-via-ldd`) still passes — its tools
      are now redundant with the in-process client, but the file
      stays as documentation of *why* this change exists.
- [ ] 6.4 Run `tests/test_spike_cancellation_flush.py` and verify
      cancellation semantics per design Open Question 3.

## 7. Out-of-scope follow-ups

- [ ] 7.1 Filed separately: removing the legacy
      `tests/test_field_logging_mcp_path.py` once the new client is
      battle-tested — its coverage is now subsumed.
- [ ] 7.2 Filed separately: extending the test client to support
      subprocess transport for tests that genuinely need a separate
      process (cold-start measurement, signal handling). Today's
      cold-start tests use subprocess directly; no API change needed
      here.
