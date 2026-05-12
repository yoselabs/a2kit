# Design — Typer-as-cli-builder spike

## Context

`src/a2kit/packages/cli/builder.py` is the largest single
hand-rolled reflection module in the project. It:

- walks tool function signatures via `inspect.signature`,
- reads pydantic `FieldInfo` from `Annotated[T, Field(...)]`,
- synthesises `click.Option` objects per parameter,
- handles body-model flattening (BaseModel → many `--flags`),
- injects `--connection` for connection-aware tools,
- wraps the function's return value through the format router
  (`a2kit.packages.formatter`).

Typer is the canonical FastAPI-style "type-hints → CLI" library
built on top of Click. The hypothesis is that Typer absorbs items
1-3 and 5 above natively, leaving a small wrapper layer for
items 4 (format routing) and 6 (connection passthrough).

## Spike sub-questions

Each sub-question must be answered with code evidence and recorded
under "Spike Findings". An unanswered sub-question is a failed
spike on that dimension.

### Q1 — Does Typer read `Annotated[T, pydantic.Field(description=...)]`?

Verify Typer surfaces the `Field.description` as the option's
`--help` text. Build a tool with one annotated parameter, invoke
`--help`, observe.

Pass criteria: `--help` shows the description verbatim. No
secondary call into `description_of()` needed.

### Q2 — Does Typer accept pydantic body models, and how?

Build a tool with `body: SomeBaseModel`. Try (a) Typer's native
support, (b) JSON-from-stdin, (c) flattened flags via a Typer
plugin or our own pre-processor.

Pass criteria: at least one of (a)/(b)/(c) ergonomically maps
to the existing flattened-flags UX. If only (c) and (c) requires
re-implementing builder.py inside the Typer plugin, this
sub-question is a NO and the spike likely fails overall.

### Q3 — Does the format-routing wrapper compose with Typer's output?

Typer prints return values via `click.echo`. The format router
emits TSV / page-tsv / JSON shaped strings. Try replacing
Typer's output stage with a `result_callback` or by returning
pre-rendered strings.

Pass criteria: the format router's existing tests all pass when
Typer drives the dispatch. No double-encoding, no surprise
`click.echo` wrapping.

### Q4 — Can `--connection` be synthesised at command-construction time?

The current builder injects `--connection` even when the tool
signature does not declare it. Typer derives options from
signatures. Three approaches: (a) inject a `connection` parameter
into a generated function wrapper before passing to Typer, (b)
add `--connection` as a Typer "context" option at the app level,
(c) require the parameter on the signature (breaking).

Pass criteria: (a) or (b) work cleanly. (c) is rejected by this
spike: we are not migrating away from synthesised wire-scope.

If the spike finds Typer can't cleanly support wire-scope
synthesis, that may be a feature: it pressures us to fix A6
(make `connection` an explicit tool parameter) sooner. Spike
result options: (i) Typer supports it natively, proceed; (ii)
Typer doesn't but can with effort, escalate to a decision —
keep magic vs. ship A6 first; (iii) Typer can't support it at
all, A6 becomes a blocker for the Typer migration.

### Q5 — Cold-start delta

Measure `time a2kit --help` and `time a2kit examples.streaming_logger run --help`
before and after the Typer prototype. v0.27.2 set the cold-start
baseline after `mcp.types` defer; we cannot regress it.

Pass criteria: Typer cold-start within 10% of current builder
cold-start, OR a clear lazy-import path identified that closes
the gap. Larger regressions are a NO.

### Q6 — Exception pipeline interaction

a2kit wraps tool exceptions through an enricher. Typer / Click
catch `click.UsageError`, `click.Abort`, and unhandled exceptions
themselves. Try: run a tool that raises a custom exception under
the Typer wrapper, observe what reaches the user.

Pass criteria: the enricher pipeline either runs unmodified, or
runs from inside a `try/except` we wrap around the Typer
invocation. Typer must not swallow exceptions before our
enricher sees them.

### Q7 — Tool-author ergonomics

Subjective but binding: pick a representative tool from
`examples/`. Re-write its router under the Typer prototype. Is
the resulting code clearer than the current shape? Does
introspection (`-> Page[Task]`, `Annotated[int, Field(...)]`)
still drive both transports without divergence?

Pass criteria: code is at least as clear, no new boilerplate
per tool. If Typer introduces decoration the author would not
have written by hand, sub-question is a NO.

Additional pass criterion for body-model UX divergence: PASS
if Typer can render Pydantic body-model fields as individual
`--flag` options (current a2kit behavior) OR if we accept a
divergence where CLI takes a JSON blob via `--input '{...}'`
and MCP keeps the structured form. FAIL if neither shape
works without significant Typer fork/patch.

## What "we reject Typer" looks like

Any of:

- Q2 has no ergonomic mapping for body-model UX.
- Q3 forces double-encoding through `click.echo`.
- Q4 requires breaking the connection-synthesis contract.
- Q5 regresses cold-start by >10% with no lazy-import remedy.
- Q6 has Typer / Click swallowing exceptions before our
  enricher sees them with no workaround.

If two or more sub-questions are NOs, the decision is **reject**
without further investigation. A single NO with a clean
work-around may still be **proceed** if the work-around is
documented.

## Risks

- **Spike scope creep.** Easy to spend three days "finishing the
  migration" instead of one day answering the questions. Mitigate
  with a hard 1-day timebox and a checklist of the seven
  sub-questions; if the answer to a question is unknown at hour
  N, that question becomes "rejected on grounds of insufficient
  evidence" and the decision uses what is known.
- **Cherry-picking a non-representative tool.** Using a trivial
  tool would over-flatter Typer. Use `streaming_logger` (has
  body args, structured returns, events) or `tracker` (has
  connection passthrough, list views).

## Positioning vs. other in-flight changes

Runs in parallel with `align-with-pydantic-and-stdlib` and
`loud-degrade-everywhere`. If the spike recommends "proceed,"
a follow-up proposal `replace-cli-builder-with-typer` lands
AFTER the v0.31.0 bundle (avoid stacking too many changes per
release).

## Timebox

One working day. Hard stop. If unfinished, record what is known
and decide on partial evidence.

## Spike Findings

[Populate during spike execution. One paragraph per Q1-Q7. End
with a single line: "Decision: proceed" or "Decision: rejected".
Reference the prototype branch by commit SHA.]

## Decision

[One of: "Proceed to `replace-cli-builder-with-typer`." or
"Rejected. Keep `cli/builder.py`. Rationale: <Q-id>: <reason>."]
