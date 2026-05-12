## Context

Round-5/6 shipped docstring → param description auto-pull as an
ergonomics affordance — eliminate `Annotated[T, a2kit.Param(...)]`
wrappers when the docstring already documents the param. The
implementation is a hand-rolled regex parser (`src/a2kit/_docstring.py`,
~100 LOC) plus annotation mutation in `_augment_annotations_from_docstring`.

Reviewing the shipped surface, the user's verdict is that the parser
itself is a "dirty approach": it adds a custom DSL parser on the hot
decoration path, picks one of three Python docstring conventions
(Google, Numpy, Sphinx) arbitrarily, silently degrades on parse
anomalies, and creates two sources of truth for parameter descriptions.

The trade we made — saving ~3 LOC per parameter in tool authoring code
— is not worth those costs. Roll back to the v0.28 contract:
parameter descriptions come from `Annotated[T, a2kit.Param(...)]` or
bare `pydantic.Field(description=...)`. Tool-level descriptions (first
docstring line + full body) are unchanged — that path doesn't need a
parser.

## Goals / Non-Goals

**Goals**

- Delete the regex-based docstring parser and all paths that consume it.
- Restore the v0.28 `tool-description-contract` surface.
- Keep the AST-static lint rule `collect_param_descriptions` (A2K006)
  — it has nothing to do with the docstring parser; it walks
  `Annotated[T, Param(description=...)]` AST nodes for cross-tool
  duplicate detection.

**Non-Goals**

- No replacement parser (Numpy, Sphinx, or third-party libraries like
  `docstring-parser` / `griffe`). The explicit-annotation surface is
  the answer.
- No deprecation cycle. `param_descriptions` was added one release ago
  (v0.29.0/0.29.1), has no known external consumers, and is a private
  test seam in practice. Direct removal under v0.30.0.

## Decisions

### Hard removal, not a deprecation

`A2KitMeta.param_descriptions` was added in v0.29.1; the docstring
parser shipped in v0.29.0. Both releases are days old. No external
consumer documented or observed. Hard removal under v0.30.0 is the
right call.

### `_stamp` no longer mutates `fn.__annotations__`

Removing the augment helper restores `_stamp` to a pure read-only path
over `fn.__annotations__`. FastMCP's schema generator continues to see
exactly what the author wrote — no hidden decoration-time mutation.

### Spec scrub

The `tool-description-contract` spec's docstring-related requirements
are removed wholesale:

- "Per-parameter descriptions resolved from the docstring"
- "Explicit Param or Field description wins over the docstring"
- "No new third-party dependency is introduced"
- "Non-goal — Numpy / Sphinx / reST docstring styles"

The first three requirements (tool-level docstring → MCP description /
CLI help, `a2kit.Param`, `pydantic.Field`) are retained — they were the
v0.28 surface.

## Risks / Trade-offs

- **Risk**: a2web (and any other consumer) re-introduces verbose
  `Annotated[...]` wrappers. **Mitigation**: that was the v0.28
  surface; the wrappers are the documented way. The CHANGELOG calls
  this out as a breaking removal.
- **Trade-off**: tools with rich Google-style docstrings no longer
  free-bee descriptions to the MCP schema. **Mitigation**: explicit
  wrappers are 1 LOC; the docstring stays as human-readable
  documentation.

## Migration Plan

Single PR under v0.30.0. CHANGELOG entry:

> **Removed**: Google-style docstring → param description auto-pull
> (shipped v0.29.0). Use `Annotated[T, a2kit.Param(description=...)]`
> or `pydantic.Field(description=...)` for parameter descriptions.

No flag, no shim. `A2KitMeta.param_descriptions` removal is the only
public-surface break.

## Open Questions

None. Removal is mechanical.
