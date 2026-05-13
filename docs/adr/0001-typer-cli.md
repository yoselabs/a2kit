# ADR 0001: Replace hand-rolled Click reflection with Typer

## Status

Accepted, 2026-05-13. Implemented in change
`replace-cli-builder-with-typer` (archived).

## Summary

In the context of the a2kit CLI builder, facing a 480-LOC hand-rolled
Click-reflection layer that accumulated a new conditional every cleanup
round, we decided for Typer (Click + a maintained reflection layer) and
against continuing to maintain our own shim, to achieve removal of the
parallel reflection layer and ecosystem alignment for the upcoming Rust
and TypeScript SDK ports, accepting a 70ms first-import cost on `typer`
and a JSON-string body-model CLI UX divergence.

## The problem

`src/a2kit/packages/cli/builder.py` had grown into ~480 LOC whose sole
job was: "look at a Python function signature, build a Click command
that matches it." Every line of it was a parallel re-implementation of
what `typer` already does, but worse, because every new pydantic /
typing pattern we wanted to support required another conditional in
`_make_tool_command`.

Concretely, by the time of the v0.31.0 bundle, the per-parameter loop
inside `_make_tool_command` was branching on six shapes:

1. `bool` produces a `--flag / --no-flag` Click switch.
2. `int | float | str` (or `Optional[...]` of one) produces a primitive
   `click.Option`.
3. `list[X] | dict[X, Y] | tuple[...]` produces `click.STRING` plus a
   JSON-decode path in the callback.
4. `Annotated[T, pydantic.FieldInfo(description=...)]` extracts the
   description and lifts it to Click's `help` kwarg.
5. `body: SomeBaseModel` walks the model's fields, synthesizes one
   Click option per field, and reassembles the BaseModel in the
   callback. ~50 LOC of code doing what pydantic already does.
6. Required-but-no-default tracks a `required_names` set, checks it in
   the callback, raises `UsageError` with a hand-formatted message.

Plus a 40-LOC `LazyGroup` class whose only purpose was to defer the
`fastmcp` import until `<app> serve` was actually invoked, because
otherwise `<app> --help` paid for fastmcp's ~1s startup.

The audit pattern was unmistakable. Every cleanup round (rounds 4, 5,
6) found new conditionals in this file. Every new pydantic v2 feature
was another conditional. The LazyGroup cache existed because the
construction itself was expensive enough to need lazy materialization.

`builder.py` was a magnet for reflection special cases. The work it
was doing has a name in the Python ecosystem, ships maintained, and
on the same Click foundation we already depend on.

## What we considered (and why Typer)

**Keep doing what we have (write better Click code).** This is what
recent cleanup rounds were doing. The conditionals kept accumulating
because the problem we were solving was not a Click problem. Click
is, by design, an imperative CLI library: you build commands either
with decorators (`@click.command`, `@click.option`) or by constructing
the objects yourself (`click.Command(name=..., params=[click.Option(...)])`).
Click does not introspect Python type annotations to decide what
options to expose. That is a deliberate scope boundary.

Our `builder.py` was the reflection layer on top of Click. We had
built and were maintaining an in-house "type hints to Click commands"
translator. That is the layer Typer provides, maintained upstream by
the FastAPI ecosystem, with `Annotated[T, typer.Option(help=...)]` as
the metadata channel.

The migration is not "swap CLI frameworks." Click stays underneath.
`CliRunner` still tests our commands. `add_command` still attaches
plugin Click commands (we use this for `connections_cli`). Env-var
expansion, exit-code semantics, exception classes all unchanged. What
changes is that we stop maintaining a translator layer between
Python's type system and Click's `click.Option` shape.

What Typer absorbs at zero cost to us:

| Old `builder.py` path | Typer equivalent |
|---|---|
| `_click_type_for(int / float / str / bool)` | Native: Typer reads the annotation. |
| `--flag / --no-flag` synthesis for `bool` | Native: bool params get the switch shape. |
| `Optional[T]` unwrap and nullable handling | Native: `T \| None` is understood. |
| Required-options check in callback | Native: `default=...` means required. |
| Default rendering in `--help` | Native: `[default: X]`. |
| `LazyGroup` cache for `serve` | Unneeded: callback bodies run on invocation, not on help. |
| Hand-rolled `--help` formatter | Native: progressive disclosure for free. |

What Typer does not absorb:

- Lifting `pydantic.FieldInfo.description` into the option's `--help`
  text. Typer reads `typer.Option(help=...)`, not pydantic's
  `Field(description=...)`. Resolved by a 30-LOC adapter at
  `src/a2kit/packages/cli/_field_to_typer.py`.
- The body-model flattening UX. We decided to drop it (see The
  decision below).
- Format routing, LDD wiring, enricher chain, dispatch hook. These
  stay in the per-tool callback exactly as before. ~80 LOC, unchanged
  in shape.

**argparse / cleo / cyclopts.** All would require a full Click to
other-framework migration, breaking `CliRunner` test helpers,
`add_command` plugin contracts, and the env-var ecosystem Click ships.
Typer is the only option that keeps Click underneath while adding the
reflection layer on top.

**A thinner in-house shim.** A shim is a shim no matter how thin. The
spike (`spike-typer-cli-replacement`, archived 2026-05-13) confirmed
Typer absorbs the work cleanly across all seven sub-questions.

**Walk `BaseModel` fields under Typer (preserve flattened flags).**
Same pydantic-walking code, just behind a Typer adapter. Saves no LOC,
asks every author to pick a mode per-tool. The single-mode JSON-string
UX described below is the actual simplification.

## The decision

Replace `src/a2kit/packages/cli/builder.py` with a Typer-driven
implementation. Each tool function is registered through
`typer.Typer.command()` with a synthesized `__signature__` and
`__annotations__` derived from its wire params. A 30-LOC adapter at
`src/a2kit/packages/cli/_field_to_typer.py` rewrites
`Annotated[T, pydantic.FieldInfo(description=...)]` into
`Annotated[T, typer.Option(help=...)]`.

`LazyGroup` is deleted. `<app> serve` is a normal Typer command whose
callback body imports `fastmcp` on invocation.

`compute_schema` moves out of `cli/schemas.py` (which never belonged
under `cli/`: pure pydantic plus typing, no Click) to a new top-level
`a2kit.schema` lazy-imported via `_LAZY_MODULES`. `cli/schemas.py` is
deleted.

`typer>=0.25,<1` becomes a runtime dependency. `import a2kit` does not
trigger `import typer` (the import lives at the top of `builder.py`,
and `a2kit.__init__` only loads that module from inside `a2kit.run`).

**Body-model UX change.** Tools with `body: SomeBaseModel` are exposed
on the CLI as a single `--body '<json>'` flag, decoded via
`SomeBaseModel.model_validate_json`. The pre-existing flattened-flag
UX is removed. In-repo blast radius is zero: no tool ships this shape.
Future authors who want flat-flag CLI ergonomics for a structured
input write the fields explicitly in the signature.

## Consequences

### Positive

- The 350 LOC of click-Option-per-parameter plumbing is gone. The
  per-tool reflection problem is now framework-owned, not project-owned.
- Future pydantic and typing features (Annotated stacking, StrEnum,
  TypeAdapter, etc.) land in Typer, not in our codebase.
- `cli/schemas.py` (179 LOC) drops to `a2kit/schema.py` (122 LOC) of
  transport-neutral schema introspection. `build_schema_command`'s 45
  LOC of Click wiring is replaced by a 25-line Typer subcommand inline.
- Three SDK ports coming (Python now, Rust, TypeScript). With Typer
  in place, each port picks its language's native CLI library
  (`clap` for Rust, `commander` or `oclif` for TS) instead of porting
  350 LOC of reflection logic three times.
- LazyGroup goes away. Cold-start for `<app> --help` is unchanged:
  Typer command callbacks do not execute their bodies during help
  rendering.

### Negative

- `typer` is a new runtime dep. `import typer` adds ~70ms on first
  import, deferred until `build_full_cli(app)` runs. `import a2kit`
  stays free of typer.
- Pydantic `BaseModel` body params lose flattened-flag CLI UX
  (`--body '<json>'` now). MCP wire shape unchanged. Zero in-repo
  callers; downstream tools using this shape must switch to the
  JSON-string form.
- Container-of-BaseModel params (`list[Item]`, `dict[str, Item]`) go
  through raw JSON decode. The tool callback receives `list[dict]` or
  `dict[str, dict]`, NOT validated pydantic instances. MCP delivers
  the same untyped shape (consistency over magic). Tool authors who
  want validation call `TypeAdapter(<ann>).validate_python` themselves
  or decompose into a `BaseModel` body.
- Typer's `--install-completion` and `--show-completion` subcommands
  are disabled (`add_completion=False`). They would otherwise pollute
  every `<app> --help` with two entries that ~95% of users never use.
  Future work may re-enable under an opt-in flag.
- Typer 1.0 is in pre-release. The `typer>=0.25,<1` upper pin guards
  against the breaking-change window. Revisit on Typer 1.0 release.

### Migration

- **Tool authors:** nothing to do.
- **CLI users of tools with `body: BaseModel`:** switch from per-field
  flags to `--body '<json>'`. Audit: zero in-repo tools match.
- **CHANGELOG:** breaking-shape note shipped with the release that
  carries this change.

## References

- Spike (decision PROCEED, all 7 sub-questions PASS):
  `openspec/changes/archive/2026-05-13-spike-typer-cli-replacement/design.md`
- Implementation proposal and spec deltas:
  `openspec/changes/archive/2026-05-13-replace-cli-builder-with-typer/`
- Code: `src/a2kit/packages/cli/builder.py`,
  `src/a2kit/packages/cli/_field_to_typer.py`, `src/a2kit/schema.py`
- ADR conventions: `docs/adr/README.md`
