# Design — pull parameter descriptions from the tool docstring

## Context

a2kit already promotes the function docstring to the canonical
**tool** description: the existing `tool-description-contract` spec
binds the dedented docstring body to both the MCP `description` field
and the click subcommand long-help. Per-parameter descriptions,
though, still live in `Annotated[T, a2kit.Param(description="...")]`
wrappers stacked on every kwarg.

Round-5 / round-6 a2web feedback (gap 4) measured the cost: a real
router's `routers.py` is roughly 80% wrapper-noise. Each tool method
ends up with a docstring `Args:` section AND a parallel set of
`Param(description=...)` decorators that copy those strings verbatim.
Authors must touch two places to add a kwarg, readers must scan two
lines to learn what each parameter does, and the wrappers visually
bury the actual types.

This change extends the docstring-is-canonical contract one level
down — to parameters — without removing `Param`. `Param` keeps its
job for genuinely explicit cases (description that disagrees with
the docstring; non-description schema metadata like `examples=`,
`ge=`, `le=`, `title=`). The win is that the common case — "the
description in `Param` matches the docstring line" — collapses to
just the docstring line.

## Goals / Non-Goals

### Goals

- At decoration time, parse the tool function's docstring and extract
  `name: description` pairs from a Google-style `Args:` block.
- Bake the extracted mapping into `A2KitMeta` so it is available to
  both the MCP schema builder and the CLI click-option builder
  without per-call cost.
- Apply the docstring description **only when** the parameter does
  not already carry an `Annotated[...]` `description=` metadata
  entry. Explicit always wins.
- Cover all four verb decorators (`@a2kit.read`, `@a2kit.write`,
  `@a2kit.tool`, `@a2kit.list_`) via the shared `_stamp` path.
- Ship without a new third-party dependency.

### Non-Goals

- Numpy-style docstrings (`Parameters\n----------\nname : type\n    desc`).
- Sphinx / reST `:param name:` field lists.
- Mixed-style docstrings or auto-detection between styles.
- Type extraction from the docstring (a2kit already takes types from
  the signature; the docstring is **descriptions only**).
- A return-value or raises-section contract (out of scope; the tool
  description spec already owns the body).
- Lint that warns when an explicit `Param(description=...)` matches
  the docstring (could be a follow-up; not in this change).

## Decisions

### D-FORMAT — Google-style only

The Google-style block is unambiguous, indentation-driven, and the
most common in modern Python tooling (mkdocstrings, pydoc-markdown,
Google's own style guide). Supporting one format keeps the parser
to ~30 LOC and removes the need to disambiguate "which style is
this docstring".

Recognised section headers (case-insensitive, trailing colon required):
`Args:`, `Arguments:`, `Parameters:`. The first matching header wins;
the section ends at the next blank-then-non-indented line, the next
recognised Google section header (`Returns:`, `Raises:`, `Yields:`,
`Examples:`, `Note:`, `Notes:`, `Attributes:`, `See Also:`), or the
end of the docstring.

Each entry in the section is a line of the form:

```
    name: description text continuing
        on the next indented line if needed.
    other_name (type): another description.
```

The optional `(type)` is parsed and **discarded** — a2kit takes
types from the signature. Continuation lines are joined with a
single space. Whitespace is collapsed.

### D-PARSER — hand-rolled, no new dep

The parsing surface is small: dedent with `inspect.cleandoc`, find the
section header line, iterate while indentation is greater than the
header's, split each entry on the first `:` outside any `(...)` type
suffix. Adding `docstring-parser` (or `griffe`) for this would be
~2 MB of transitive deps for a function that fits in a screen.

The helper lives at `src/a2kit/_docstring.py` (leading underscore —
internal). Public surface stays the same; nothing is re-exported.

### D-PRECEDENCE — explicit always wins

The decoration pipeline resolves each kwarg's description in this
order, first hit wins:

1. `Annotated[T, FieldInfo(description=...)]` with a non-`None`
   `description` (this covers both `a2kit.Param(description=...)`
   and any bare `pydantic.Field(description=...)`).
2. Docstring `Args:` entry for that kwarg name.
3. No description.

Rationale: the docstring is a fallback so authors who **want** to
diverge can. It also keeps the change zero-risk for every existing
tool — anything that worked yesterday still produces the same MCP
schema today.

### D-TIMING — decoration-time only

Parsing runs inside `_stamp`, before constructing `A2KitMeta`. The
result is a `Mapping[str, str]` (parameter name → resolved
description) frozen onto `A2KitMeta.param_descriptions`. The MCP
schema builder reads this mapping when it builds the input schema;
the CLI click-option builder reads it when it builds the
subcommand. Neither path touches the docstring at request time.

If the docstring is missing, malformed, or contains no `Args:`
section, the mapping is empty and behaviour is identical to today.
Parse failures SHALL NOT raise — a malformed docstring is a
description-loss event, not a crash.

### D-SCOPE — kwargs only, by parameter name

Only **keyword parameters** (positional-or-keyword and
keyword-only) are eligible. `self`, `*args`, `**kwargs`, and any
`ctx: ToolContext` parameter SHALL be ignored even if they appear
in the `Args:` block.

The lookup is by name. Unknown names in `Args:` (a parameter
documented but no longer in the signature) SHALL be silently
ignored; signature names with no `Args:` entry SHALL fall through
to "no description". A future lint can warn on either gap; this
change ships behaviour, not lint.

### D-CONFLICT-MESSAGES — silent precedence

When both an explicit `Param(description=...)` and a matching
docstring entry exist, the explicit value wins **silently**. No
warning, no debug log. Reasoning: a2web routers will routinely have
both during migration (drop one wrapper at a time); noisy warnings
would create a transient mess in agent-side stderr that the user
cannot easily silence.

A lint rule that flags "your `Param` description matches your
docstring; you can drop the wrapper" is a natural follow-up — it
belongs in `a2kit lint`, not in the runtime.

## Risks & Trade-offs

- **R1 — Wrong format picked.** Google-style is a real
  commitment. If a consumer's codebase is Numpy-styled, they get no
  benefit from this change and must either rewrite docstrings or
  keep using `Param`. Mitigation: the spec explicitly names
  Google-style; documentation and examples will use it; `Param`
  remains supported.
- **R2 — Parser brittleness.** A hand-rolled parser will miss
  edge cases (deeply nested code blocks inside descriptions, weird
  indentation). Mitigation: parse failures degrade silently to "no
  description"; explicit `Param` is always an escape hatch.
- **R3 — Description drift.** With both sources permitted, a
  docstring and an explicit `Param` can disagree. Mitigation:
  explicit-wins is documented in the spec; a future lint can
  reconcile.
- **R4 — Type-hint leak.** Google-style supports `name (type):`.
  We discard the `(type)` — but if an author writes a malformed
  type expression there, the discard step must still split cleanly.
  The parser splits on the first `:` after the close of the first
  balanced `(...)` group; if no balanced group exists, on the first
  `:` of the line.

## Migration Plan

This is a purely additive change. No deprecation, no breaking
behaviour. After it lands:

1. New tool methods can omit `Param(description=...)` and write the
   description in the `Args:` block instead.
2. Existing tool methods continue to work. Authors may delete
   redundant `Param(description=...)` wrappers at leisure; the
   docstring will pick up the slack.
3. a2web's `routers.py` is the canonical migration target — the
   feedback that drove this change.

No data migration, no version-pinning concerns, no API surface
change beyond the new (optional) `param_descriptions` attribute on
`A2KitMeta`.

## Open Questions

- Should `@a2kit.list_`'s `selectable_fields` / `default_fields`
  positional args participate? They're not kwargs, so under D-SCOPE
  they don't. Leaving as-is.
- Should the resolver also read `Param(...)` positional shorthand
  (`Param("desc")`)? Yes — the existing `description_of` helper
  already handles both forms, so the precedence rule reuses it.
