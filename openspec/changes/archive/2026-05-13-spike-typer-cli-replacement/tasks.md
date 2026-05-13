# Tasks — Typer-as-cli-builder spike

## 0. Prerequisites

- [x] 0.1 Prototype location: `/tmp/a2kit-typer-spike/` (not committed; see
      design.md "Spike Findings" for evidence per Q).
- [x] 0.2 Baseline cold-start recorded (see Q5).
- [x] 0.3 Representative router: `examples/streaming_logger` (Q7 rewrite),
      `examples/tracker` for connection-passthrough reference (Q4).

## 1. Q1 — Pydantic Field description as --help

- [x] 1.1 Confirmed Typer does NOT read `pydantic.Field(description=...)`
      natively; a ~10-line Annotated-metadata adapter that rewrites
      `Field` into `typer.Option(help=...)` makes it work.
- [x] 1.2 Reported in design.md Q1 paragraph.

## 2. Q2 — Body model handling

- [x] 2.1 Typer-native: `RuntimeError: Type not yet supported`.
- [x] 2.2 JSON-from-string flag works. Flattened-flags require walking the
      BaseModel and synthesizing one Typer Option per field.
- [x] 2.3 Reported in design.md Q2 paragraph. Spike picks JSON-string
      divergence (allowed by design.md Q7 alt criterion).

## 3. Q3 — Format routing composition

- [x] 3.1 Command body owns the `typer.echo(format_response(...).data)`
      path. No `result_callback` needed.
- [x] 3.2 Verified JSON output composes cleanly; same call shape the
      existing builder uses.
- [x] 3.3 Reported in design.md Q3 paragraph.

## 4. Q4 — Connection synthesis

- [x] 4.1 Approach (a) — synthesize a wrapper function with
      `__signature__`/`__annotations__` carrying the extra parameter —
      works.
- [x] 4.2 Verified the wrapper strips `connection` from kwargs before
      calling the underlying tool.
- [x] 4.3 Reported in design.md Q4 paragraph.

## 5. Q5 — Cold-start delta

- [x] 5.1 Measured uv-driven wall clock: baseline ~1337ms median, Typer
      ~1283ms median (within noise).
- [x] 5.2 `python -X importtime`: typer module ~70ms cold. Click already
      imported. Net delta ~58ms (well under 10% of baseline).
- [x] 5.3 No lazy-import work needed.
- [x] 5.4 Reported in design.md Q5 paragraph.

## 6. Q6 — Exception pipeline

- [x] 6.1 KeyError raised inside the Typer-driven tool.
- [x] 6.2 Enricher wrapping fn ran and replaced the message.
- [x] 6.3 Typer's missing-option error produces clean Click-style output;
      Rich-traceback default is off-by-flag (`pretty_exceptions_enable=False`).
- [x] 6.4 Reported in design.md Q6 paragraph.

## 7. Q7 — Tool-author ergonomics

- [x] 7.1 streaming_logger tools re-run unmodified through the prototype
      adapter; the boilerplate moves to a `make_typer_command` helper
      (~70 LOC) that replaces the current ~350 LOC builder.
- [x] 7.2 The only Typer-specific decoration is hidden inside the adapter
      (synthesized Annotated metadata). Tool authors see no Typer surface.
- [x] 7.3 Reported in design.md Q7 paragraph.

## 8. Decision

- [x] 8.1 Decision recorded in design.md: PROCEED.
- [x] 8.2 Scope summary drafted for follow-up `replace-cli-builder-with-typer`.
- [ ] 8.3 N/A — decision is proceed.

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
