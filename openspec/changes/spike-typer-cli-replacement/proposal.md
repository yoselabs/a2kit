# Spike: replace cli/builder.py with Typer

## Why

`src/a2kit/packages/cli/builder.py` is 350+ LOC of hand-rolled Click
integration. It parses each tool's function signature, reads
`pydantic.FieldInfo` out of `Annotated[T, Field(description=...)]`,
synthesises a `click.Option` per parameter, and stitches the options
into a `click.Command`. Typer's entire reason for existing is to do
exactly this from native type hints, with pydantic-Field support and
docstring-derived `--help` text.

If Typer can carry our load, ~350 LOC of bespoke reflection
disappear, the Python CLI lands on a well-known idiom rather than an
in-house DSL, and the porting tax for the planned Rust/TS SDKs
shrinks (each picks its own native CLI library; the wrapper layer
gets thinner because there is no longer a hand-built reflection layer
to port-or-replace).

But there are real unknowns. The CLI builder is doing more than
"signature → flags":

1. **Body-model flattening.** Today the builder flattens
   `data: SomeBaseModel` into a series of `--field` flags rather than
   accepting a single JSON blob. Typer accepts pydantic models as
   parameter types but its default UX is JSON-on-stdin or a single
   string flag, not flattened.
2. **Format-routing wrapper.** Tool return values are routed through
   `a2kit.packages.formatter` per the `type-driven-format-routing`
   capability (TSV / page-tsv / JSON). Typer prints whatever the
   command function returns via `click.echo` by default. The two
   output paths need to compose without fighting.
3. **Wire-scope synthesis.** Connection-aware tools auto-receive a
   `connection: str` kwarg from `--connection` even when the tool's
   signature does not list it. The current builder synthesises that
   option at command-construction time. Typer's option declaration
   is normally tied 1:1 to the function signature.
4. **Cold start.** `cli/builder.py` already lazy-imports Click. Typer
   imports Click + Rich + Typer's own runtime. The v0.27.2 cold-start
   release explicitly defers `mcp.types`; we cannot regress here.
5. **Exception pipeline.** a2kit has an enricher pipeline that wraps
   raised exceptions before they reach the user. Typer / Click do
   their own exception handling (`click.UsageError`, `click.Abort`,
   etc.). The interaction is unclear.
6. **Pydantic Field reading.** Typer is documented to read pydantic
   `Field(description=...)` for some shapes but not for arbitrary
   `Annotated[T, Field(...)]` on bare parameters. Needs verification.
7. **Pydantic body-model in MCP path.** The CLI flattens body models;
   the MCP path takes them as a single structured arg. If we replace
   the CLI builder with Typer the divergence between transports must
   stay invisible to the tool author.

This proposal is a **research spike, not an implementation**. It
exists to track the work and produce a single deliverable: a
written decision in this change's `design.md` of "proceed to
migration" or "rejected, keep `cli/builder.py`, with rationale per
sub-question". Spike budget: roughly 1 day. No production code
changes; the only output is the decision artifact.

If the decision is "proceed", a follow-up change
`replace-cli-builder-with-typer` will carry the actual migration
with spec deltas (most likely against `verb-decorators` and
`tool-description-contract`). If "rejected", the design.md captures
which sub-question(s) were the hard NOs so the next attempt does
not re-relitigate them.

## What Changes

- Build a throwaway Typer wrapper around one representative router
  (suggestion: `examples/streaming_logger`, because it exercises
  body-model args, structured returns, and connection passthrough).
- Answer the seven unknowns above with code-backed evidence
  (working prototype, benchmark numbers for cold-start, exception
  trace observation).
- Record findings in `design.md` under "Spike Findings", one
  paragraph per sub-question.
- Conclude with a decision: **proceed** or **rejected**.
- Capture the spike output as a `spike-deliverables` capability —
  the only spec delta in this change — so `openspec validate
  --strict` has a delta to inspect and the deliverable is binding
  (the spike SHALL produce a written decision; an empty design.md
  is a failed spike).

This change ships NO production code. The throwaway prototype lives
in a scratch branch, is not merged, and is referenced from
`design.md` by commit SHA.

## Capabilities

### Added Capabilities

- `spike-deliverables` — declares that this change's only
  deliverable is a written decision in `design.md`, with explicit
  pass/fail criteria. No runtime behaviour. The capability exists
  so the spike has a checkable artifact and so future spikes can
  reuse the same shape.

## Impact

- **Affected code**: none in `main`. Throwaway prototype lives in
  a scratch branch referenced by commit SHA from `design.md`.
- **APIs**: none changed.
- **Dependencies**: none added to the project (Typer is evaluated
  but not adopted by this change).
- **Risk**: zero — the change cannot land broken code because it
  lands no code. The only risk is a sloppy decision document, which
  the `spike-deliverables` capability's pass/fail scenarios guard
  against.
- **Follow-up if proceed**: `replace-cli-builder-with-typer` change
  with deltas on `verb-decorators`, `tool-description-contract`,
  and possibly `cli-response-encoding`.
- **Follow-up if rejected**: a one-paragraph "why we keep
  builder.py" note added to the relevant module docstring so the
  next reader who has the same hypothesis can find the rationale
  without re-running the spike.
- **Coordination**: independent of `explicit-router-surface` and
  `align-with-pydantic-and-stdlib`. If either lands before this
  spike, the prototype just absorbs the new shapes (explicit
  `tools` tuple, typed extras, `pydantic.Field` instead of
  `a2kit.Param`); none of those change the sub-questions above.
