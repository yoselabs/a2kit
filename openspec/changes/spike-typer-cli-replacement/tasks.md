# Tasks — Typer-as-cli-builder spike

## 0. Prerequisites

- [ ] 0.1 Create a scratch branch `spike/typer-cli` off `main`. The
      prototype lives here; nothing merges from this branch.
- [ ] 0.2 Record baseline cold-start: `hyperfine 'a2kit --help'`,
      capture median + stddev into `design.md` "Spike Findings"
      under Q5 baseline.
- [ ] 0.3 Pick the representative router. Default:
      `examples/streaming_logger`. If it does not exercise
      connection passthrough, swap to `examples/tracker`. Record
      the choice in `design.md`.

## 1. Q1 — Pydantic Field description as --help

- [ ] 1.1 Write a Typer tool with one
      `Annotated[int, pydantic.Field(description="batch size")]`
      parameter. Run `--help`. Confirm description appears.
- [ ] 1.2 Report finding in `design.md` Q1 paragraph.

## 2. Q2 — Body model handling

- [ ] 2.1 Add a tool with `body: TaskCreateBody` (existing model
      in the chosen example). Try Typer-native model support.
- [ ] 2.2 If (a) doesn't work, try JSON-on-stdin and flattened
      flags via a small pre-processor.
- [ ] 2.3 Report finding in `design.md` Q2 paragraph. Note which
      approach (a/b/c) works and whether it preserves UX.

## 3. Q3 — Format routing composition

- [ ] 3.1 Pipe a tool's return through the existing
      `a2kit.packages.formatter` instead of Typer's default
      `click.echo`. Try `result_callback` and direct pre-render.
- [ ] 3.2 Run the format-routing test subset against the
      prototype. Confirm TSV / page-tsv / JSON outputs match.
- [ ] 3.3 Report finding in `design.md` Q3 paragraph.

## 4. Q4 — Connection synthesis

- [ ] 4.1 Inject `--connection` as a Typer-level option that
      flows through context, OR generate a wrapped function with
      the synthesised parameter. Pick whichever is cleaner.
- [ ] 4.2 Verify the wrapped tool body receives `connection: str`
      via DI exactly as it does under the current builder.
- [ ] 4.3 Report finding in `design.md` Q4 paragraph.

## 5. Q5 — Cold-start delta

- [ ] 5.1 `hyperfine 'a2kit-typer --help'` against the prototype.
- [ ] 5.2 Compare to 0.2 baseline. Compute % delta.
- [ ] 5.3 If >10% regression, profile via `python -X importtime`
      to identify lazy-importable modules. Document.
- [ ] 5.4 Report finding in `design.md` Q5 paragraph with
      numbers.

## 6. Q6 — Exception pipeline

- [ ] 6.1 Write a tool that raises a custom exception type. Run
      under the Typer wrapper.
- [ ] 6.2 Confirm the existing enricher sees the exception.
- [ ] 6.3 Confirm `click.UsageError` (e.g. missing required
      option) still produces helpful output, not a raw traceback.
- [ ] 6.4 Report finding in `design.md` Q6 paragraph.

## 7. Q7 — Tool-author ergonomics

- [ ] 7.1 Re-write the chosen router's tools under the Typer
      prototype. Diff before/after LOC.
- [ ] 7.2 Identify any Typer-specific decoration that would
      surprise a tool author.
- [ ] 7.3 Report finding in `design.md` Q7 paragraph.

## 8. Decision

- [ ] 8.1 Fill in `design.md` "Decision" line with either
      "Proceed to `replace-cli-builder-with-typer`." or
      "Rejected. Keep `cli/builder.py`. Rationale: <reason>."
- [ ] 8.2 If "Proceed", draft a one-paragraph scope summary for
      the follow-up change (which capabilities will get deltas,
      breaking-change posture, release target).
- [ ] 8.3 If "Rejected", append a one-paragraph note to
      `src/a2kit/packages/cli/builder.py`'s module docstring so
      the next reader who has the same hypothesis finds the
      rationale without re-running the spike.

## 9. Archive

- [ ] 9.1 Tag the prototype branch's last commit and reference
      its SHA from `design.md`.
- [ ] 9.2 Archive this change via `openspec archive
      spike-typer-cli-replacement`.
- [ ] 9.3 After the spike's decision is recorded in `design.md`,
      the `spike-deliverables` capability is moved to
      `openspec/specs/spikes/` (a new namespace) OR deleted from
      the spec set on archive. This keeps the main
      `openspec/specs/` directory clean of one-off spike
      artifacts. Coordinate with the openspec maintainer (likely
      the user) on which path.
