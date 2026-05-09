## Why

LDD today gives the agent two channels: **logs** (`ctx.info` / `warning` /
`error`) and **numeric progress** (`ctx.report_progress(i, total)`). Neither
fits the case "tell the agent *what* you found, mid-flight, with structure" —
e.g. "found 3 duplicates", "switched to fallback API", "batch 4 of 7 yielded
12 rows". Authors today either fold this into log strings (lossy, agent
treats them as ambient telemetry) or buffer everything into the final
return (latency hit, agent can't react until the call completes).

The `streaming_logger` LDD example demonstrates the pattern but stops at log
lines. We want a typed mid-flight reporting channel — the tool keeps a normal
`async def f(...) -> Result:` shape, and emits zero-or-more typed `Report`
payloads via `ctx.report(...)`. Reports stream **immediately** over the same
notification channel `ctx.info` already uses (works on stdio AND HTTP) — no
buffering, no SSE-only requirement.

## What Changes

- Add `ctx.report(payload: ReportT)` to the `ToolContext` Protocol. Both
  adapters (FastMCP / CLI) implement it. On MCP, emits an
  `notifications/message` with `level="report"` and the structured payload.
  On CLI, prints to stderr (same channel as `ctx.info`).
- Add `ctx.event(name: str, **payload: Any)` for typed narrative events
  ("api.fetched", "fallback.used", "phase.complete"). Distinct from
  `ctx.info` because it's structured-by-default — payload is a dict, not a
  formatted string. Routed through the same notification path; `level="event"`.
- Add an optional `report=ReportT` kwarg to `@a2kit.read` / `@a2kit.write` /
  `@a2kit.list_` / `@a2kit.tool`. When set, `ctx.report(payload)` validates
  `isinstance(payload, ReportT)` (Pydantic model or dict-with-`TypedDict`) and
  the tool's schema dump documents the report shape under
  `meta.a2kit.report_schema`.
- Add a lint rule `A2K-LDD-REPORT-TYPE` — fires when a tool calls
  `ctx.report(...)` but its decorator has no `report=` kwarg, OR when the
  declared `ReportT` is not module-scope (same constraint as Pydantic return
  types — see ANTIPATTERNS #2).
- Extend `examples/streaming_logger/` to demonstrate `ctx.report` + `ctx.event`
  alongside the existing `ctx.info` / `report_progress` calls. The README
  contrasts when each channel is the right pick.
- Document the four channels in `README.md` "Logging + progress" section:
  `ctx.info` (process telemetry), `ctx.event` (typed milestones),
  `ctx.report` (typed mid-flight result chunks), `ctx.report_progress`
  (numeric progress).

## Capabilities

### New Capabilities

- `ldd-streaming-reports`: typed mid-flight reporting via `ctx.report(...)`,
  including the report-type contract on the verb decorators, schema
  documentation, and lint rule.
- `ldd-narrative-events`: typed narrative events via `ctx.event(name, **payload)`,
  routed through the MCP notification channel as a distinct level.

### Modified Capabilities

- `thin-core-surface`: extends the `ToolContext` Protocol with two new
  methods (`report`, `event`) and the verb decorators with an optional
  `report=` kwarg.

## Impact

- **Code**: `src/a2kit/tool.py` (decorator kwargs + meta plumbing),
  `src/a2kit/packages/mcp/context.py` (new methods on the context impl),
  `src/a2kit/packages/cli/context.py` (CLI mirror — stderr writer),
  `src/a2kit/metadata.py` (report_schema field on `A2KitMeta`),
  `src/a2kit/packages/lint/rules/shape.py` (new A2K-LDD-REPORT-TYPE rule).
- **Tests**: `tests/test_app.py` and `tests/packages/{mcp,cli}/test_context.py`
  pick up the new methods; `tests/packages/lint/test_rules_shape.py` covers
  the new rule; `tests/examples/streaming_logger/` extended.
- **Docs**: `README.md` (four-channel table), `CHANGELOG.md` (next-version
  entry), `examples/streaming_logger/README.md` (when-to-use guide), new
  ANTIPATTERNS entry on "don't fold structured findings into log strings."
- **Backwards compat**: fully additive. Existing tools without `report=`
  unaffected. `ctx.report` on a tool without `report=` raises
  `ReportTypeNotDeclared` at call time — tools that don't use it are
  silent.
- **Cold-start**: zero impact — `ctx.event` and `ctx.report` are method
  additions to the existing context impls, no new transitive imports.
