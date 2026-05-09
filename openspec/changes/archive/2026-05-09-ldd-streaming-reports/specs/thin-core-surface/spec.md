## MODIFIED Requirements

### Requirement: `ToolContext` Protocol exposes protocol-neutral logging + progress

`a2kit.ToolContext` SHALL be a `Protocol` (runtime-checkable not required)
that defines the channels through which a tool body communicates with the
caller mid-flight. Both adapters (`packages/mcp/context.py`,
`packages/cli/context.py`) SHALL provide concrete implementations.

The Protocol SHALL define **four** mid-flight channels:

1. **Process telemetry** — `info(msg, **kw)`, `warning(msg, **kw)`,
   `error(msg, **kw)`. Free-form log lines; agent treats them as ambient.
2. **Numeric progress** — `report_progress(current, total)`. Agent shows a
   bar / percentage.
3. **Narrative events** — `event(name, **payload)`. Typed milestone with a
   stable name and structured payload. Distinct level on the wire.
4. **Typed reports** — `report(payload)`. Mid-flight typed result chunks;
   declared via the verb decorator's `report=ReportT` kwarg. Validated at
   call time. Distinct level on the wire.

All four channels SHALL emit immediately — no buffering, no end-of-call
collection. On MCP transport, all four flow through the same
`notifications/message` mechanism with distinct `level` values. On CLI,
all four write to stderr (interleaved with the tool's stdout return).

#### Scenario: All four channels exist on the Protocol
- **WHEN** `ToolContext`'s public methods are inspected
- **THEN** `info`, `warning`, `error`, `report_progress`, `event`, `report` are all present

#### Scenario: MCP and CLI implementations both honor all channels
- **WHEN** the same tool fn runs via FastMCP serve and via CLI invocation
- **THEN** `ctx.info`, `ctx.warning`, `ctx.error`, `ctx.report_progress`, `ctx.event`, `ctx.report` all succeed in both modes

#### Scenario: Reports without declared report= kwarg raise
- **WHEN** a tool body calls `ctx.report(...)` and the decorator has no `report=ReportT` kwarg
- **THEN** `ReportTypeNotDeclared` is raised inside the tool body

### Requirement: Verb decorators map to MCP `ToolAnnotations` + tags + report schema

`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, and `@a2kit.tool` SHALL be
thin sugar over `FastMCP.tool(annotations=..., tags=...)`. Each verb
decorator SHALL be implementable in ≤ 15 lines.

The decorators SHALL accept an optional `report=ReportT` kwarg. When set,
`ReportT` SHALL be stamped onto `A2KitMeta.report_schema` (the JSON schema
dict). When unset, `report_schema` is `None`.

#### Scenario: read maps to readOnlyHint=True
- **WHEN** a function is decorated with `@a2kit.read`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`

#### Scenario: write maps to readOnlyHint=False, destructiveHint=True
- **WHEN** a function is decorated with `@a2kit.write`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=False, destructiveHint=True)`

#### Scenario: report= kwarg recorded on meta
- **WHEN** `@a2kit.read(report=BatchReport)` decorates a function
- **THEN** `fn._a2kit.report_schema` contains the JSON schema dict for `BatchReport`
