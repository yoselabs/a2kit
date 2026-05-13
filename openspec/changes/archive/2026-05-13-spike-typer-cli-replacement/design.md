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

Prototype location: `/tmp/a2kit-typer-spike/` (not committed; throwaway
artefacts referenced per Q). Typer 0.25.1 added to dev deps only.
Representative router for Q7: `examples/streaming_logger` (body args,
structured returns, LDD-aware); `examples/tracker` referenced for the
connection-passthrough shape exercised in Q4.

### Q1 — Pydantic Field description as --help: PASS (with adapter)

Typer does NOT read `pydantic.Field(description=...)` natively. With a
bare `Annotated[int, Field(description="batch size")]` parameter, Typer's
`--help` shows just `--batch-size INTEGER [default: 100]` — no description.
A ~10-line Annotated-metadata adapter that rewrites each `FieldInfo` whose
`.description` is set into a `typer.Option(help=<that description>)` makes
the help text appear verbatim. The adapter is trivial and lives inside the
new builder, so tool authors keep writing `pydantic.Field` exactly as today.
This is a NO at the native level and a PASS with a clean workaround that
costs ~10 LOC.

### Q2 — Body-model handling: PASS (with documented divergence)

Typer-native (`def f(body: TaskCreateBody)`) raises `RuntimeError: Type not
yet supported` — Typer/Click has no built-in pydantic adapter. Two
fallbacks both work: (a) JSON-from-string `--body '{"…"}'`, decoded inside
the command callback via `TaskCreateBody.model_validate_json`; (b)
flattened flags, which means walking the BaseModel fields at command-build
time and synthesizing one Typer Option per field — i.e. re-implementing
the current `builder.py` body-model flattening logic inside the Typer
adapter. Approach (a) is ~5 LOC per body-model parameter and matches the
divergence design.md Q7 explicitly allows ("CLI takes a JSON blob via
`--input '{...}'` and MCP keeps the structured form"). Approach (b)
preserves the current flattened-flags UX but costs roughly the same lines
of code we save elsewhere. The spike picks (a) as the recommended path,
noting that (b) remains available if user research shows agents prefer
flattened flags on the CLI.

### Q3 — Format-routing composition: PASS

Easiest pattern: the command body owns its own
`typer.echo(format_response(result, format_hint=fmt).data)` call. Typer
only auto-echoes when a command returns a `str` AND a `result_callback`
is registered; the command body returning `None` after explicit echo is
exactly the pattern current `builder.py` uses with Click. Verified end
to end in `q3_format_routing.py`: a `list[dict]` return flows through
`format_response` and lands on stdout with no double-encoding and no
surprise wrapping. No need for Typer's `result_callback` — that hook
exists for the top-level Typer app and per-command return-passthrough is
not idiomatic Typer anyway.

### Q4 — Connection synthesis: PASS

Approach (a) from the design — synthesize a wrapper function with
`__signature__` and `__annotations__` carrying an extra `connection`
parameter — works without ceremony. Typer's introspection reads
`__signature__` and `Annotated` metadata; the wrapper strips
`connection` from kwargs before calling the real tool fn. Verified
in `q4_connection.py`: a tool whose source signature is
`def tool(*, project_id: str | None = None)` exposes `--connection` (required)
and `--project-id` on the CLI, the wrapper captures `--connection`,
forwards `--project-id`. Missing `--connection` produces a clean
"Missing option '--connection'" error. Approach (b) — Typer-level
context option — would work too but spreads the wire-scope logic across
two surfaces; approach (a) keeps it per-command. No need to change
the connection-synthesis contract; A6 is not pressured by this spike.

### Q5 — Cold-start delta: PASS

`python -X importtime` shows `import typer` costs ~70ms cold (typer.main
~30ms, typer.completion ~3ms, shellingham ~1ms, typer.core/Click already
required). End-to-end wall-clock under `uv run` for a script that does
`import a2kit + import examples.tracker + build_full_cli` measures
roughly 1337ms median; the same imports with a Typer-shaped wrapper
in place of `build_full_cli` measure roughly 1283ms median. The two
distributions overlap completely (variance dominated by `uv run`
startup). Worst credible interpretation: ~70ms typer-only delta on a
~1.3s baseline = ~5%, well under the 10% threshold. The current
LazyGroup pattern (deferring `serve` / `fastmcp`) ports unchanged to
Typer via `lazy_subcommands` or `add_typer` on a callback. No regression.

### Q6 — Exception pipeline: PASS

Wrapping the tool fn with the enricher BEFORE passing to Typer (exactly
the same `_wrap_with_enricher` pattern in current `builder.py`) means
the enricher sees raised exceptions before Typer/Click do. Verified in
`q6_exceptions.py`: a `KeyError('abc')` becomes
`KeyError("tracker resource 'abc' not found (enriched)")` after the
wrapper rewrites it. For UsageError-class problems (missing required
option) Typer produces a clean Click-style error message; we never
reach the enricher and don't want to. Typer's default Rich-rendered
traceback for uncaught exceptions is suppressed with
`Typer(pretty_exceptions_enable=False)` — we'd set this once at the
top-level app construction site. No exceptions are swallowed before
the enricher; Typer plays nicely with the existing pipeline.

### Q7 — Tool-author ergonomics: PASS

`q7_streaming_logger_under_typer.py` registers the streaming_logger
`import_csv` and `quick_status` tools unchanged — same kwonly signature,
same docstring-as-help, same `dict` return — through a single
`make_typer_command(app, fn)` adapter (~70 LOC) that handles:
Annotated-Field-to-typer-Option rewriting (Q1), body-model JSON decoding
(Q2), format routing (Q3), connection synthesis (Q4), enricher wrapping
(Q6). Compared to the current `builder.py` (~350 LOC including LazyGroup,
markdown stripping, click.Option construction, JSON decoding glue, schema
flag, format flag, dispatch hook integration), the Typer-based adapter
covers the same surface in roughly 80-100 LOC — call it ~250 LOC net
reduction, with the saved code being the boring "construct a click.Option
per parameter" plumbing. Tool author surface is identical: they never
see Typer. `from typer import Option/Typer` appears exactly once, inside
the adapter. The router-level `tools = (...)` tuple, the
`@a2kit.read()` / `@a2kit.write()` decorators, the kwonly `ctx`/`store`
DI parameters all carry through untouched.

Decision: proceed.

## Decision

Proceed to `replace-cli-builder-with-typer`.

Rationale: All seven sub-questions are PASS. Q1 and Q2 carry workarounds
(Annotated adapter, JSON-string body divergence) that cost roughly 15
LOC combined and have no impact on tool-author code. The remaining
sub-questions are clean. Estimated net LOC delta for the follow-up:
`-350 +100 = -250` LOC across `src/a2kit/packages/cli/builder.py` plus
a small (~30 LOC) `_field_to_typer.py` helper that owns the
Annotated-metadata rewrite. The follow-up proposal
`replace-cli-builder-with-typer` would carry spec deltas against
`verb-decorators` and `tool-description-contract` (the documented
JSON-string body UX shift), plus a new `cli-response-encoding` note
that the body-model UX is now `--<name> '<JSON>'` on the CLI and
unchanged on MCP. Non-breaking for tool authors; user-visible CLI
breaking change for any caller currently using flattened flags for a
body parameter (low blast radius — the only example exercising this
shape is the tracker `bulk_import_tasks` `titles: list[str]` parameter,
which is already JSON-encoded today since lists go through the
`complex_json` path). Release target: post-v0.31.0 (next available
slot, do not stack with the v0.31.0 bundle).
