# ADR 0001 — Replace hand-rolled Click reflection with Typer

## Status

Accepted. Implemented in `replace-cli-builder-with-typer` (2026-05-13).

## The problem

`src/a2kit/packages/cli/builder.py` had grown into ~480 LOC whose sole
job was: "look at a Python function signature, build a Click command
that matches it." Every line of it was a parallel re-implementation of
what `typer` already does, but worse — because every new pydantic /
typing pattern we wanted to support required *another* conditional in
`_make_tool_command`.

Concretely, by the time of the v0.31.0 bundle, the per-parameter loop
inside `_make_tool_command` was branching on six shapes:

1. `bool` → synthesize `--flag / --no-flag` Click switch.
2. `int | float | str` (or `Optional[...]` of one) → primitive `click.Option`.
3. `list[X] | dict[X, Y] | tuple[...]` → `click.STRING` + a JSON-decode
   path in the callback.
4. `Annotated[T, pydantic.FieldInfo(description=...)]` → extract the
   description, lift it to Click's `help` kwarg.
5. `body: SomeBaseModel` → walk the model's fields, synthesize one
   Click option per field, reassemble the BaseModel in the callback
   (~50 LOC of code that did nothing pydantic didn't already do).
6. Required-but-no-default → mark in a `required_names` set, check in
   the callback, raise `UsageError` with a hand-formatted message.

Plus a 40-LOC `LazyGroup` class whose only purpose was to defer the
`fastmcp` import until `<app> serve` was actually invoked, because
otherwise `<app> --help` paid for fastmcp's ~1s startup.

The audit pattern was unmistakable. Every cleanup round found new
conditionals in this file. Every new pydantic v2 feature (StrEnum,
`Annotated` stacking, `TypeAdapter`) was another conditional. The
LazyGroup cache logic existed because the construction itself was
expensive enough to need lazy materialization.

`builder.py` was a magnet. The work it was doing — read signatures,
emit a CLI — has a canonical Python solution that ships maintained,
tested, and on the same Click foundation we already depend on.

## What Typer absorbs for free

| Old `builder.py` code path | Typer equivalent |
|---|---|
| `_click_type_for(int / float / str / bool)` | Native: Typer reads the annotation. |
| `--flag / --no-flag` synthesis for `bool` | Native: bool params get the switch shape. |
| `Optional[T]` unwrap + nullable handling | Native: `T \| None` is understood. |
| Required-options check in callback | Native: `default=...` means required, with a clean error. |
| Default rendering in `--help` | Native: `[default: X]`. |
| `LazyGroup` cache for `serve` | Unneeded: callback bodies run on invocation, not on help. |
| Hand-rolled `--help` formatter (`format_commands`) | Native: progressive disclosure for free. |

What Typer *doesn't* absorb:

- Lifting `pydantic.FieldInfo.description` into the option's `--help`
  text. (Typer reads `typer.Option(help=...)`, not pydantic's
  `Field(description=...)`.) → a 30-LOC adapter at
  `src/a2kit/packages/cli/_field_to_typer.py`.
- The body-model flattening UX. We decided to drop it (see below).
- Format routing + LDD wiring + enricher chain + dispatch hook. These
  stay in the per-tool callback exactly as before. ~80 LOC, unchanged
  in shape.

## Decision

Replace `builder.py` on top of `typer.Typer`. Each tool gets a
synthesized function with `__signature__` and `__annotations__`
matching its wire params; that function goes through
`typer_app.command()`. The Annotated rewrite lives in one place
(`_field_to_typer.py`). LazyGroup is deleted; `<app> serve` is a
normal Typer command whose callback body imports fastmcp on first
invocation.

`compute_schema` moves out of `cli/schemas.py` (it never belonged
under `cli/` — pure pydantic + typing, no Click) to a top-level
`a2kit.schema` lazy-imported via `_LAZY_MODULES`. `cli/schemas.py` is
deleted.

`typer>=0.25,<1` is a runtime dep. `import a2kit` does NOT trigger
`import typer` (the import lives at the top of `builder.py`, and
`a2kit.__init__` only loads that module from `a2kit.run`).

### Body-model UX: drop the flattening, take the JSON-string divergence

The pre-Typer code path for `body: SomeBaseModel` walked the model
fields and synthesized one Click option per field
(`--name`, `--qty`, `--description`, …), then reassembled the
BaseModel before calling the tool. That was the ~50 LOC of pydantic
introspection that wasn't paying for itself.

Under Typer, the equivalent code path is essentially the same line
count — re-implementing pydantic walking inside a Typer plugin — so
the migration would save nothing. We picked the alternative the spike
explicitly opened up: expose `body` as a single
`--body '<json>'` string flag, decoded via
`SomeBaseModel.model_validate_json(value)`.

In-repo blast radius: zero. No tool in the codebase declares
`body: BaseModel` as a kwonly parameter today; every "structured input"
tool already takes explicit kwonly fields (`title: str, priority: int`)
because that's also the shape the MCP wire wants.

The trade-off: future tool authors who *want* a flattened-flag CLI for
a structured input write the fields explicitly in the signature, not
as a `BaseModel` body. Same shape on both transports, no per-tool mode
selector. Documented in the `tool-description-contract` and
`verb-decorators` spec deltas.

## Consequences

Positive:

- ~480 LOC of `builder.py` becomes ~530 LOC of *Typer-driven*
  `builder.py`, but the *meaningful* delta is different: the 350 LOC
  of click-Option-per-parameter plumbing is gone; what remains is
  callback logic that was always going to exist (format routing,
  LDD, enricher chain, dispatch hook). Future pydantic / typing
  features land in Typer, not here.
- `cli/schemas.py` (179 LOC) drops to `a2kit/schema.py` (122 LOC) —
  pure compute_schema with no Click dependency; the `build_schema_command`
  factory is replaced by a 25-line Typer subcommand inline in `builder.py`.
- Three SDK ports coming (Python now, Rust, TypeScript). With Typer
  in place, each port picks its language's native CLI library
  (`clap` for Rust, `commander` or `oclif` for TS) instead of porting
  350 LOC of reflection logic three times. The reflection contract
  becomes "introspect a function signature and emit a CLI" — language
  primitive, not framework primitive.
- LazyGroup goes away. Cold-start for `<app> --help` is unchanged —
  the deferral now comes from Typer command callbacks not executing
  their bodies during help rendering.

Negative:

- Typer is a new runtime dep. `import typer` adds ~70ms on first import,
  deferred until `build_full_cli(app)` runs. `import a2kit` stays free.
- Pydantic `BaseModel` body params lose flattened-flag CLI UX
  (`--body '<json>'` now). MCP wire shape unchanged. Zero in-repo
  callers; new authors choose explicit kwonly fields for flat-flag UX.
- Container-of-BaseModel params (`list[Item]`, `dict[str, Item]`) go
  through raw JSON decode — the tool callback receives
  `list[dict]` / `dict[str, dict]`, NOT validated pydantic instances.
  MCP delivers the same untyped shape (consistency over magic). Tool
  authors who want validation call `TypeAdapter(<ann>).validate_python`
  themselves or decompose into a `BaseModel` body.
- Typer's `--install-completion` / `--show-completion` subcommands are
  disabled (`add_completion=False`). They would otherwise pollute every
  `<app> --help` with two entries that 95% of users will never use.
  Future work may re-enable under an opt-in flag.
- Typer 1.0 is in pre-release. The `typer>=0.25,<1` upper pin guards
  against the breaking-change window; revisit on Typer 1.0 release.

## Alternatives considered

**Keep `builder.py` as-is.** The shape that pushed us off this path: the
file grew with every cleanup round, and three SDK ports coming meant
re-implementing the same accidental complexity in two more languages.

**argparse / cleo / cyclopts.** Typer is the established FastAPI sibling
on top of Click. We already depend on Click; Typer is the smallest jump
that absorbs the most reflection code. Other libraries would either
require a Click → other migration (more breakage) or duplicate Click's
ecosystem coverage (worse story for shell integration, plugin authors,
testing helpers).

**A thinner in-house shim.** A shim is a shim no matter how thin; the
maintenance cost of explaining "why not Typer?" doesn't go away. The
spike confirmed Typer absorbs the work cleanly.

**Walk `BaseModel` fields at command-build time** (preserve flattened
flags). Same code, just behind a Typer adapter. Saves no LOC, asks every
author to pick a mode. The single-mode JSON-string UX is the actual
simplification.

## References

- Spike (decision: PROCEED, all 7 sub-questions PASS):
  `openspec/changes/archive/2026-05-13-spike-typer-cli-replacement/design.md`
- Implementation:
  `openspec/changes/archive/2026-05-13-replace-cli-builder-with-typer/`
- Code: `src/a2kit/packages/cli/builder.py`,
  `src/a2kit/packages/cli/_field_to_typer.py`, `src/a2kit/schema.py`
