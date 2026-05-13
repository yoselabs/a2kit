# ADR 0001 — Replace hand-rolled Click reflection with Typer

## Status

Accepted. Implemented in change `replace-cli-builder-with-typer`.

## Context

`src/a2kit/packages/cli/builder.py` was the single largest reflection module
in the project: roughly 350 lines walking tool signatures via
`inspect.signature`, reading `pydantic.FieldInfo` from
`Annotated[T, Field(...)]`, synthesizing one `click.Option` per parameter,
flattening `BaseModel` body params, injecting `--connection`, and
threading the format-routing wrapper.

The pre-v0.32 FastMCP-magic-ceiling audit flagged this file as the
largest single non-orthogonal seam in the package. Every new wire-scope
or annotation pattern landed there; every new option required hand-wired
Click plumbing. The same logic — "type hints in, CLI out" — has a
canonical Python solution (Typer, FastAPI's CLI sibling) that we were
re-implementing badly.

A timeboxed spike (`spike-typer-cli-replacement`, archived
2026-05-13) tested seven sub-questions against the existing CLI
contract: pydantic-Field-as-help, body-model handling, format routing,
connection synthesis, cold-start delta, exception pipeline, and
tool-author ergonomics. All seven PASSed, two with small workarounds
documented as `--help`-adapter (~10 LOC) and the body-model JSON-string
divergence (Q2). Spike decision: PROCEED.

## Decision

Replace `src/a2kit/packages/cli/builder.py` with a Typer-driven
implementation. Each tool function is registered through
`typer.Typer.command()` with a synthesized `__signature__` and
`__annotations__` derived from the wire params. A ~30 LOC adapter at
`src/a2kit/packages/cli/_field_to_typer.py` rewrites
`Annotated[T, pydantic.FieldInfo(description=...)]` into
`Annotated[T, typer.Option(help=...)]` so Typer surfaces the description
as the option's `--help` text.

Add `typer>=0.25,<1` as a runtime dependency. `import a2kit` continues
to NOT trigger `import typer` (the import lives at the top of
`a2kit.packages.cli.builder`, and `a2kit.__init__` only loads that
module from inside `run()`).

Body-model parameters (`body: SomeBaseModel`) are exposed on the CLI as
a single JSON-string flag `--body '<json>'` and decoded via
`SomeBaseModel.model_validate_json`. MCP wire shape is unchanged. The
previous flattened-flag-per-field UX is removed; in-repo blast radius
is zero (no in-repo tool ships this shape today).

Move `compute_schema` from `a2kit.packages.cli.schemas` to a new
transport-neutral core module `a2kit.schema`, lazy-imported via
`_LAZY_MODULES`. Delete `a2kit.packages.cli.schemas`. Public re-export
`a2kit.testing.compute_schema` is preserved.

## Consequences

Positive:

- Roughly 250 LOC net deleted from the CLI package, with the saved code
  being the boring "construct a click.Option per parameter" plumbing.
- Alignment with the FastAPI-ecosystem standard: future tool-authors and
  contributors recognise the Typer idiom.
- The Rust and TypeScript SDK ports can each pick their language's
  native CLI library independently rather than carrying a custom
  reflection layer ported three times.
- `compute_schema` lives in `a2kit.schema` where it always belonged:
  transport-neutral, no `click` import, no `mcp` coupling.
- LazyGroup goes away; `serve` cold-start invariant is preserved by the
  fact that Typer command callbacks only execute their body on
  invocation.

Negative:

- Typer is a new runtime dependency (`typer>=0.25,<1`). Click is already
  a runtime dep and Typer is built on Click; `import typer` adds ~70ms
  cold-start cost, deferred until `build_full_cli(app)` is called.
- Pydantic-`BaseModel` body parameters lose their flattened-flag CLI UX
  and become `--body '<json>'`. Authors who want flat-flag CLI ergonomics
  decompose the body into explicit kwonly params in the tool signature.
- The Typer 1.0 breaking-change window is open; the `<1` upper pin
  guards. Revisit on Typer 1.0 release.

## Alternatives considered

**Keep `builder.py` as-is.** Rejected: the spike showed Typer is mature
enough to absorb the work, and every new wire-scope or annotation
pattern landed in this file. The maintenance trajectory was bad.

**argparse / cleo / cyclopts.** Rejected: Typer is the established
FastAPI sibling, aligns with pydantic idioms, and is what an ecosystem
contributor coming from the FastAPI / FastMCP world expects to see.

**Build a thinner in-house shim.** Rejected: doesn't address the
ecosystem-standard alignment goal. A custom shim is a custom shim no
matter how thin; the cost of explaining "why not Typer?" never goes
away.

**Walk `BaseModel` fields at command-build time** (preserve flattened
flags). Rejected: re-implements the current `builder.py` body-model
flattening logic inside the Typer adapter, paying the same maintenance
cost the migration is supposed to eliminate. The single-mode JSON-string
UX is the actual simplification.

## References

- Spike: `openspec/changes/archive/2026-05-13-spike-typer-cli-replacement/design.md`
- Implementation: `openspec/changes/replace-cli-builder-with-typer/`
  (proposal.md, design.md, tasks.md, specs/)
- Code: `src/a2kit/packages/cli/builder.py`,
  `src/a2kit/packages/cli/_field_to_typer.py`, `src/a2kit/schema.py`
