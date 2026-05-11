# Tasks — field-logging via LDD primitive

## 0. Prerequisites

- [x] 0.1 Baseline: `uv run pytest --no-cov` green; `make lint` green;
      record current `ty check examples/` error count (14, all
      kwargs-on-Context shapes per design D-SIG-TEST).
- [x] 0.2 Document the MCP-side crash with a repro test that we
      expect to fail today and pass after this change:
      `tests/test_field_logging_mcp_path.py` — calls a tool that
      does `await a2kit.ldd.info(ctx, "hi", k=1)` via a real
      `fastmcp.Client(transport=build_mcp_server(app))`. Today's
      `ctx.info("hi", k=1)` shape would crash this; the new free
      function must round-trip.

## 1. Library — `a2kit.ldd.log` and convenience aliases

- [x] 1.1 Add `log(ctx, level, msg, /, **fields)` to
      `src/a2kit/packages/ldd/__init__.py` per design D-LDD-LOG.
      Internal dispatch via existing `_is_fastmcp_context`.
- [x] 1.2 Implement MCP path: build `extra` from `fields` plus the
      `elapsed_ms` basis from the LDD context-var (or
      `_APP_START_MONOTONIC` fallback); cap `msg` via `_cap_text`
      before delivery (design D-MSG-CAP, D-EXTRA-BASIS); call
      `await ctx.log(level=level, message=capped, extra=extra)`.
- [x] 1.3 Implement CLI path: identity-check
      `isinstance(ctx, StderrToolContext)`; call
      `ctx._emit(LEVEL_LABEL, msg, fields, elapsed_ms=...)`.
- [x] 1.4 Add `info`, `warning`, `error`, `debug` convenience
      wrappers in the same module. Each accepts both string and
      instance forms (D-LDD-LOG).
- [x] 1.4a Extract the string/instance discriminator from
      ``a2kit.ldd.event`` into a shared helper
      (``_resolve_payload(name_or_instance, **kwargs) -> (str, dict)``)
      and call it from both ``event`` and ``log``. The pydantic /
      dataclass / vars / Enum-unwrap coercion rules SHALL live in
      exactly one place.
- [x] 1.4b Test instance-form parity: ``log(ctx, "info", MyDC(x=1))``
      delivers the same wire payload as
      ``log(ctx, "info", "MyDC", x=1)`` on both transports.
- [x] 1.5 Export `log`, `info`, `warning`, `error`, `debug` from
      `a2kit.ldd.__all__`.
- [x] 1.6 Honor the `--no-events` / `A2KIT_LDD=off` kill-switches
      consistently with `event`/`report` (decide whether `log` is
      gated by the events flag, the reports flag, or a new
      `--no-log` flag; default: shares the events flag).

## 2. Library — narrow `StderrToolContext` logging methods

- [x] 2.1 Rewrite `StderrToolContext.info/warning/error/debug` per
      design D-CTX-INFO. Signature matches
      `fastmcp.Context.info(message, logger_name=None, extra=None)`.
      Body forwards to `self._emit(LEVEL, message, extra_with_logger)`.
- [x] 2.2 Add a `# why:` comment block above the four methods noting
      that fielded narrative logging now lives on `a2kit.ldd.log` to
      prevent the divergence regrowing.
- [x] 2.3 Run `uv run python -c "from a2kit.packages.cli.context import StderrToolContext; import inspect, fastmcp; ..."`
      assertion: `inspect.signature(StderrToolContext.info) ==
      inspect.signature(fastmcp.Context.info)` (modulo `self`).

## 3. Library — rebuild `_CapturingContext`

- [x] 3.1 Confirm `_CapturingContext` doesn't depend on the widened
      `info` signature in its own override layer (it overrides
      `_emit` only — should be a no-op verification).
- [x] 3.2 If structured-capture (`list[LogLine]`) is selected per
      design Open Question 2, refactor capture from `list[str]` to a
      named-tuple list. Otherwise leave rendering capture as-is.
- [x] 3.3 Update `tests/test_in_process_client.py` to use
      `await a2kit.ldd.info(ctx, "starting", batch=1)` instead of
      `await ctx.info("starting", batch=1)`. Same for `warning`.
- [x] 3.4 Verify the existing capture assertions
      (`client.events`, `client.progress`, etc.) still pass against
      the migrated call sites.

## 4. Examples — migrate call sites

- [x] 4.1 `examples/streaming_logger/routers.py` — replace all 8
      `await ctx.info(...)` / `ctx.warning(...)` / `ctx.error(...)`
      kwarg calls with `await a2kit.ldd.info(ctx, ...)` etc. Update
      module-top imports: `from a2kit import ldd`.
- [x] 4.2 `examples/tracker/routers.py` — single call at line ~118
      rewritten the same way.
- [x] 4.3 `examples/streaming_logger/README.md` — narrative LDD
      examples updated.
- [x] 4.4 `examples/tracker/README.md` — single doc example updated.
- [x] 4.5 Run `make examples` and the in-process client tests for
      both — confirm green.
- [x] 4.6 Run `uv run python -m examples.streaming_logger.server
      serve` smoke-test against a real `fastmcp.Client` (the
      `tests/test_field_logging_mcp_path.py` repro from 0.2 covers
      this).

## 5. Tests — signature-compatibility

- [x] 5.1 Rewrite `tests/test_context_surface.py` per design
      D-SIG-TEST. Add a `CALL_SHAPES` registry of `(method, args,
      kwargs)` tuples mined from `tests/` and `examples/`.
- [x] 5.2 Assertion: each call shape's signature binds against both
      `fastmcp.Context.<method>` and `StderrToolContext.<method>`
      via `inspect.signature(...).bind(None, *args, **kwargs)`.
- [x] 5.3 Keep the existing `test_stub_covers_fastmcp_context_surface`
      as a sibling test — name-coverage + MCP_ONLY allowlist.
- [x] 5.4 Add `tests/test_field_logging_mcp_path.py` from 0.2 if not
      already in place — the end-to-end repro that proves the new
      free function round-trips through a real fastmcp.Client.

## 6. Lint — gate `tests/` and `examples/`

- [x] 6.1 `make lint` target gains `uv run ty check examples/`. Run;
      expect 0 errors after migration.
- [ ] 6.2 `make lint` target gains `uv run ty check tests/`. If the
      diff surfaces unrelated errors (per design Open Question 3),
      either fix them inline or defer `tests/` to a follow-up
      change and leave only `examples/` gated. Decide based on
      noise.
- [x] 6.3 Update `Makefile` `lint` recipe.

## 7. Spec edits

- [ ] 7.1 `openspec/specs/mcp-context-passthrough/spec.md` — narrow
      the "CLI stub supplies a fastmcp.Context-shaped stub" requirement
      to match fastmcp's exact signature for the four logging methods.
      Remove the worked example `ctx.info("hi", x=1)`.
- [ ] 7.2 Same spec — extend "LDD event and report primitives are
      protocol-neutral functions" to cover `log` as a third sibling.
      Add MCP-path scenario: `a2kit.ldd.info(ctx, "msg", k=1)` over
      `fastmcp.Client` produces a `notifications/message` with
      `extra={"k": 1, "elapsed_ms": ...}`.
- [ ] 7.3 Same spec — add a new requirement: "Field-bearing
      logging lives on `a2kit.ldd.*`, not on `ctx.*`." with the
      antipattern listed.

## 8. Documentation

- [x] 8.1 `README.md` LDD section: document `event` / `report` / `log`
      as three siblings; show before/after for the kwarg pattern.
- [x] 8.2 `ANTIPATTERNS.md`: new entry "Kwargs on `ctx.info/warning/error/debug`."
- [ ] 8.3 `CHANGELOG.md`: BREAKING entry for the kwarg removal;
      migration recipe.

## 9. Verification

- [x] 9.1 Full suite: `make test` + `make lint` green.
- [x] 9.2 The MCP-path repro test (0.2) passes.
- [x] 9.3 Visual sanity check: run streaming_logger CLI + MCP paths,
      diff the rendered output — both should carry the same fields.
- [x] 9.4 Search the tree for any remaining `await ctx.(info|warning|
      error|debug)\(.*,.*=` patterns: `grep -rEn "await ctx\.(info|
      warning|error|debug)\([^)]*=" src tests examples` — should
      return only `extra=` matches, no other kwargs.

## 10. Out-of-scope follow-ups (captured, not done here)

- [x] 10.1 Filed as separate change: address Tier 3/4 drifts —
      `elicit`, `read_resource`, `get_prompt`, `log`, `sample*`,
      `send_notification`, `send_log_message`. The signature-test
      registry from 5.1 is the gate that will catch their
      re-introduction.
- [x] 10.2 Filed as separate change: replace `_CapturingContext`'s
      CLI-subclass anchoring with a real `fastmcp.Context`-backed
      in-process server (closes the "structural test-client is CLI"
      gap entirely, beyond just signature alignment).
