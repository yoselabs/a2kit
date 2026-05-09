## Context

LDD ("logging-driven development") is a2kit's pattern for tools that
behave like long-running pipelines: they emit progress + narrative as
they work, so the agent doesn't have to wait silently for a 30-second
call to complete. v1.0 ships `examples/streaming_logger/` showing the
pattern with `ctx.info` + `report_progress` — but those two channels
are insufficient for two recurring needs:

1. **"Tell me what you found, mid-flight, with structure."** The
   author wants to push a typed payload to the agent before the tool
   completes — e.g. "I just imported batch 4 of 7; it had 12 accepted
   rows and 0 rejected" — and have the agent be able to programmatically
   react. Today this is folded into log strings and lost.

2. **"Tell me what's happening right now, by name."** Distinct from
   logs (free-form telemetry the agent ignores), the author wants to
   emit named milestones the agent can pattern-match: `"api.fetched"`,
   `"fallback.used"`, `"phase.complete"`. Logs are noise; events are
   structure.

The user explicitly rejected the AsyncIterator/yield design when asked,
because the result type and the report type are *distinct types*. Mixing
them through one yield-stream forces a sum type or a sentinel. Using a
side-channel (`ctx.report(...)`) keeps the function signature
`async def f(...) -> Result:` untouched — the report stream is orthogonal
to the return type.

The user also clarified that reports should disable-able (kill-switch),
because in some contexts (CI logs, batch jobs, automated harnesses) the
notification noise is unwanted.

### Constraints

- Must not break existing tools — purely additive on the Protocol.
- Must work on stdio AND HTTP MCP transports — no SSE-only feature.
- Must work on the CLI runtime too (mirror to stderr).
- Must not load any new transitive imports — cold-start budget unchanged.
- Must not require typing the report payload at the call site (the
  `report=ReportT` decorator kwarg captures the contract once).

## Goals / Non-Goals

**Goals:**
- Add `ctx.report(payload)` and `ctx.event(name, **payload)` to the
  `ToolContext` Protocol.
- Add the `report=ReportT` decorator kwarg + JSON-schema stamping.
- Add a runtime kill-switch (env var, CLI flag, `app.set_ldd(...)`).
- Add lint rule `A2K-LDD-REPORT-TYPE`.
- Update the streaming_logger example + README to demonstrate.

**Non-Goals:**
- Async-generator tools (`async def f(...) -> AsyncIterator[Item]`).
  Considered and rejected: the report-type separation makes
  `ctx.report` a cleaner fit. Async-yield can return as a separate
  proposal if real demand surfaces.
- Per-tool customization of the wire-level notification shape.
  All four channels share `notifications/message`; only `level` differs.
- Subscribing to events from another tool. Events are write-only; they
  flow to the MCP client, not to other tools.
- Replay / persistence. Reports + events are ephemeral — no storage,
  no audit log. Authors who need persistence can write a separate
  router that consumes their own emissions.

## Decisions

### Decision 1: `ctx.report` is the side-channel, not `yield`

The user's "what about yield with async" framing was the primary design
fork. Considered both:

- **Option A: AsyncIterator return type.** `async def f(...) -> AsyncIterator[Item]`
  with `yield item` inside the body. Rejected because the result type and
  report type are distinct — yield-streaming forces them into one
  iterator (sum type, sentinel, or two iterators).

- **Option B: `ctx.report(payload)` side-channel (Recommended).** Tool
  body retains `async def f(...) -> Result:`. `ctx.report(payload)` is
  orthogonal to the return. Two distinct types preserved.

Option B wins. Function signature stays maximally familiar; reports are
opt-in per-call; result-vs-report separation is enforced by the language
(parameters of distinct methods).

### Decision 2: Reports flow through MCP `notifications/message`, not a custom notification

FastMCP's `Context` already routes `info` / `warning` / `error` through
`notifications/message` with `level` field. Adding `level="report"` and
`level="event"` extends that channel rather than creating a parallel one.

- **Pros**: Stdio + HTTP both work natively; no new transport code; no
  client-side compat work for adapters that already handle log
  notifications.
- **Cons**: `level` is technically constrained by spec — we treat
  `report` and `event` as a2kit extensions. The MCP client SDK ignores
  unknown levels by default, so unsupporting clients see them as
  unstructured logs (graceful degradation).

The fallback degradation is a feature: tools authored with `ctx.report`
are still useful even when the consumer hasn't upgraded to handle the
new levels.

### Decision 3: `report=ReportT` is on the verb decorator, not on the param

Considered `*, report: BatchReport = ReportChannel(...)` (parameter-default
form, mirroring `Depends`). Rejected because:

1. Reports aren't *received* by the function — they're *emitted*. A
   parameter-injection metaphor doesn't fit.
2. The decorator already carries the verb / annotations / tags — adding
   `report=` keeps the LDD contract in one place, near the read/write
   choice it relates to.
3. The `ReportT` type is needed at schema-dump time (for
   `<app> schema <tool>`) — easier to retrieve from `tool._a2kit.report_schema`
   than to re-introspect the signature.

### Decision 4: Kill-switch precedence — flag > app config > env

When all three are set, the most-specific wins:

```
CLI flag (--no-reports)  >  app.set_ldd(reports=False)  >  A2KIT_LDD=off
```

Rationale: env is the broadest knob (CI/CD wide), app is medium (per-server
config), flag is per-invocation. Most-specific wins is the standard
override hierarchy. If only one is set, that one decides.

### Decision 5: Disabled emission still validates types

Counterintuitive but important: when reports are disabled,
`ctx.report(payload)` still runs `isinstance(payload, ReportT)` and raises
`ReportTypeMismatch` on failure. Without this, tests with the env var set
would silently accept type-broken `ctx.report` calls and the bug would
only surface in production where reports are enabled.

The performance cost is one isinstance check per call — negligible.

### Decision 6: Events are unguarded; reports are typed

Asymmetric by design:
- `ctx.event(name, **payload)` — any tool can emit, no decorator kwarg
  required, no schema validation. The `name` is the contract; payload
  is documentary.
- `ctx.report(payload)` — requires `report=ReportT` on the decorator,
  type-checked at call time, schema dumped under
  `meta.a2kit.report_schema`.

The asymmetry maps to the use case: events are narrative (cheap, free),
reports are structured findings (typed, contract-bound).

### Decision 7: Lint rule fires on the body's call site, not the decorator

`A2K-LDD-REPORT-TYPE` is an AST walker that:
1. Finds tool functions (decorated by `@a2kit.{read,write,list_,tool}`)
2. Walks the body for `await ctx.report(...)` calls
3. If found AND the decorator has no `report=` kwarg → fire on the
   call site (not the decorator), because the call site is what the
   author sees in editor errors

The rule lives in `lint/rules/shape.py` (already covers similar AST
walks for A2K002/003).

### Decision 8: Wire format — relative `s.mmm`, terse text

Both adapters SHALL emit timestamps as **elapsed seconds with millisecond
precision** (e.g., `+1.234`), measured from tool-call start. Considered
alternatives:

- Absolute wall-clock (`HH:MM:SS.mmm`): noisy; agents don't care what
  hour it is. Rejected.
- Raw milliseconds (`1234ms`): hard for humans + agents to scan when
  durations span 10ms–10min. Rejected.
- Relative `s.mmm` with `+` prefix (Recommended): trivially scannable;
  signals "elapsed" without ambiguity; same width across the call.

CLI stderr column format:

```
[ +0.012 event   ] api.fetched count=30
[ +1.234 report  ] BatchReport batch=4 accepted=12
[ +1.235 INFO    ] processing batch
[ +1.250 progress] 4/7
```

The level column is left-padded to 8 chars for column alignment. The
elapsed timestamp is right-padded to 6 chars (covers up to 999.999s ≈ 16
min — enough; anything longer should probably be a job, not a tool).

On the MCP wire, the elapsed time is sent as `data.elapsed_ms` integer
milliseconds. The client picks its own rendering. We document a
recommended client-side format in the README so different MCP clients
converge.

The text portion (event name / report class name / log message) is kept
**short by convention** — guideline ≤ 60 chars. Not enforced. The
readme + ANTIPATTERNS document the rationale: long log lines cost agent
context-window tokens proportionally; one terse named event with
structured payload beats one long sentence with embedded numbers.

### Decision 9: No middleware change for the kill-switch

The kill-switch lives inside the `ToolContext` impl (mcp/cli), not as a
FastMCP middleware. Reasoning: middleware operates on tool inputs/outputs
— ctx-channel emission isn't a middleware-shaped concern. Two-line check
inside the impl: `if not self._ldd_enabled: return`.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| MCP clients not handling `level="report"` / `level="event"` | They degrade to "unknown level" → rendered as unstructured log. Documented in README. |
| Tools accidentally pushing PII via `ctx.report` | Same risk as `ctx.info` today — out of scope. Document recommendation: don't emit untrusted user data without redaction. |
| Kill-switch precedence confusion | Single sentence in README; ANTIPATTERNS entry "don't rely on env-only kill-switch in test code." |
| `ReportTypeMismatch` raised inside tool body surprises authors | Document explicitly in README + streaming_logger example. The error is the same shape as a Pydantic validation error. |
| Cold-start regression from new methods on context impls | Both impls are already loaded when the corresponding adapter is loaded — no new transitive imports. Verified via existing cold-start test. |
| Adding `event(name, ...)` overlaps with structured `info("event", **kw)` | Documented in README: events have a stable `name` field on the wire (distinct from a free-form first arg to `info`); agents can filter by name. |

## Migration

Fully additive. Existing tools work unchanged. The new features are
opt-in:
- Tools that don't call `ctx.report` / `ctx.event` are byte-identical.
- Tools that adopt `ctx.report` add `report=BatchReport` to the
  decorator — one-line change.
- Tests using `make_test_app(...)` get the new context impls
  automatically.

## Open Questions

- Should `ctx.event` payload be required (always at least `{}`)? Leaning
  yes — keeps the wire shape uniform.
- Should the runtime auto-emit a synthetic event `tool.completed` on
  every tool return? Convenient for agents that want to know "tool
  finished" without parsing the result. Probably yes, configurable via
  `app.set_ldd(emit_lifecycle_events=True)` (default off — opt-in).
  Defer to apply time.
- Should `ctx.report` accept a list of payloads in one call? E.g.
  `await ctx.report([r1, r2, r3])` for batched emission. Marginal
  utility; defer.
