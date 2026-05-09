## ADDED Requirements

### Requirement: `ctx.report(payload)` emits typed mid-flight result chunks

The `ToolContext` Protocol SHALL expose `async def report(self, payload: ReportT) -> None`.
Calling `ctx.report(payload)` from inside a tool body SHALL push the payload
to the MCP client **immediately** (no buffering, no end-of-call collection),
using the same notification channel as `ctx.info`. The notification SHALL
carry `level="report"` and the structured payload as the message body.

The tool's normal `return Result` is independent of how many `ctx.report`
calls were made. `Result` and `ReportT` are distinct types.

#### Scenario: Tool emits a report mid-flight; client receives it before the tool returns
- **WHEN** a tool calls `await ctx.report(BatchReport(batch=4, accepted=12, rejected=0))` and then continues for another 3 seconds before returning
- **THEN** the MCP client receives the `notifications/message` payload within milliseconds, not after the 3-second delay

#### Scenario: Tool reports zero times → client sees only the final return
- **WHEN** a tool never calls `ctx.report`
- **THEN** no report notifications are emitted; the agent sees only the tool's `Result`

#### Scenario: CLI runtime mirrors reports to stderr
- **WHEN** the same tool is invoked via `<app> tasks import-csv ...` (CLI mode, not serve)
- **THEN** each `ctx.report` call writes a line to stderr, distinguishable from `ctx.info` output

### Requirement: `report=ReportT` decorator kwarg declares the report contract

`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, and `@a2kit.tool` SHALL accept
an optional `report=ReportT` kwarg. When set, `ctx.report(payload)` SHALL
runtime-check that `isinstance(payload, ReportT)` (Pydantic model) or the
payload conforms to the declared `TypedDict`. Failure SHALL raise
`ReportTypeMismatch`.

The declared `ReportT` SHALL be stamped onto `A2KitMeta.report_schema` (a
JSON-schema dict produced via Pydantic's `.model_json_schema()` for models,
or `typing.get_type_hints` walk for `TypedDict`).

#### Scenario: report= kwarg captured on the tool meta
- **WHEN** `@a2kit.read(report=BatchReport)` decorates a function
- **THEN** `tool._a2kit.report_schema` contains the JSON schema for `BatchReport`

#### Scenario: ctx.report with mismatched type raises at call site
- **WHEN** the tool declares `report=BatchReport` and the body calls `await ctx.report({"random": "dict"})`
- **THEN** `ReportTypeMismatch` is raised inside the tool body — the agent sees a normal tool error envelope

#### Scenario: ctx.report without declared report= raises ReportTypeNotDeclared
- **WHEN** the tool has no `report=` kwarg and the body calls `await ctx.report(anything)`
- **THEN** `ReportTypeNotDeclared` is raised — encourages explicit declaration

### Requirement: Report schema surfaces in `<app> schema <tool>` output

The `<app> schema <tool>` CLI command SHALL include the report schema (when
declared) as a sibling of the tool's input/output schema. TOON / JSON
formatting both SHALL render it.

#### Scenario: Schema dump includes report shape
- **WHEN** a tool is decorated with `report=BatchReport` and `<app> schema my_tool` is invoked
- **THEN** the output has a `report_schema:` section showing `BatchReport`'s fields

### Requirement: Wire format — terse text + relative `s.mmm` timestamps

Reports and events SHALL be rendered with a relative timestamp measured
from tool-call start, formatted as `s.mmm` (seconds with three decimal
places — e.g., `0.123`, `12.450`). Absolute wall-clock timestamps are
NOT used: agents reason better about *elapsed* time inside a single
call than about absolute time.

The text portion (the human-facing message; for events the `name` is
the text, for reports the type's `__class__.__name__`) SHALL be kept
short — guideline ≤ 60 chars. The runtime SHALL NOT enforce a hard
cap, but the README + ANTIPATTERNS SHALL document the convention.

CLI rendering (stderr lines) format:

```
[ +0.012 event ] api.fetched count=30 source=primary
[ +1.234 report] BatchReport batch=4 accepted=12 rejected=0
[ +1.235 INFO  ] processing batch
[ +1.250 progress] 4/7
```

The `+` prefix on the timestamp is intentional — it signals "elapsed
since call start". Padding aligns columns for scannability. The `level`
column is fixed-width (≤ 8 chars).

MCP wire (`notifications/message`) SHALL include the elapsed-ms value
under `data.elapsed_ms` (integer milliseconds) — the client is free to
re-render in its preferred precision.

#### Scenario: CLI report line carries elapsed time
- **WHEN** a tool calls `await ctx.report(BatchReport(...))` 1234 ms after the call started
- **THEN** the stderr line begins with `[ +1.234 report]`

#### Scenario: MCP report payload carries elapsed_ms
- **WHEN** the same call happens over MCP transport
- **THEN** the `notifications/message` `data` dict includes `elapsed_ms: 1234`

#### Scenario: Long messages are not auto-truncated
- **WHEN** an event name or report payload exceeds the 60-char convention
- **THEN** no truncation happens — the convention is documented, not enforced

### Requirement: Reports and events can be globally disabled

The runtime SHALL honor a kill-switch that disables `ctx.report` and
`ctx.event` emission without the tool body knowing. When disabled, both
calls become no-ops — they return immediately, perform no validation,
emit no notification.

The kill-switch SHALL be controllable via:

1. **Environment variable** `A2KIT_LDD=off` — disables both reports and
   events for the entire process. Read once at app construction.
2. **CLI flag** `--no-reports` (and `--no-events`) on every subcommand
   that runs a tool — overrides the env var per-invocation.
3. **App-level method** `app.set_ldd(reports=False, events=False)` —
   programmatic control, useful for tests and scripts that consume the
   App directly.

Disabling SHALL still type-check `ctx.report(payload)` calls (so a lint
rule can fire even with reports disabled), but the actual notification
emission is skipped.

#### Scenario: Env var disables emission
- **WHEN** the process starts with `A2KIT_LDD=off` and a tool calls `await ctx.report(BatchReport(...))`
- **THEN** no notification is sent; the tool continues normally; the call returns in microseconds

#### Scenario: --no-reports CLI flag overrides env
- **WHEN** the user invokes `<app> tool --no-reports ...` (with `A2KIT_LDD` unset)
- **THEN** `ctx.report` calls are no-ops for that invocation only

#### Scenario: Disabling does NOT skip type validation
- **WHEN** reports are disabled and the body calls `ctx.report({"wrong": "type"})` against a declared `ReportT`
- **THEN** `ReportTypeMismatch` is still raised — disabling stops emission, not validation

#### Scenario: app.set_ldd toggles both
- **WHEN** `app.set_ldd(reports=False, events=False)` is called before serve/cli runs
- **THEN** both channels are no-ops for the lifetime of that App instance

### Requirement: Lint rule `A2K-LDD-REPORT-TYPE` enforces declaration discipline

A new static rule `A2K-LDD-REPORT-TYPE` SHALL fire when:
- A tool body calls `ctx.report(...)` but the decorator omits `report=`, OR
- The declared `ReportT` is defined inside a function or class body (not at
  module scope) — Pydantic forward-ref resolution constraint, mirrors
  ANTIPATTERNS #2.

#### Scenario: Missing report= kwarg fires the rule
- **WHEN** the lint rule scans a file containing `await ctx.report(...)` in a tool body whose decorator has no `report=`
- **THEN** the rule emits one finding pointing at the `ctx.report` call site

#### Scenario: Module-scope ReportT silent
- **WHEN** `class BatchReport(BaseModel)` is at module scope and used as `report=BatchReport`
- **THEN** the rule does not fire
