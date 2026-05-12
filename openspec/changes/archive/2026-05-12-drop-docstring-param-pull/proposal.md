## Why

The docstring → param description auto-pull (round-5/6 item, shipped
v0.29.0) is a regex-based extractor for Google-style `Args:` blocks. It
adds a hand-rolled parser to the hot decoration path, silently degrades
on malformed docstrings, and creates two sources of truth for parameter
descriptions (docstring text vs. `Annotated[T, Param(...)]`). User
verdict: dirty approach, not worth the LOC saved per tool.

Drop it. Tool authors annotate parameter descriptions with
`Annotated[T, a2kit.Param(description="...")]` or
`pydantic.Field(description="...")` — the same surface that was always
authoritative.

## What Changes

- **Remove `_docstring.py`** — the regex-based Google-style parser.
- **Remove `_augment_annotations_from_docstring`** and the WARN_ONCE
  helper from `src/a2kit/tool.py`. `_stamp` no longer mutates
  `fn.__annotations__` at decoration time.
- **Remove `A2KitMeta.param_descriptions`** field — was only populated
  from the docstring parser.
- **Remove docstring-pull tests**: `tests/test__docstring.py`,
  `tests/test_param_docstring_pull.py`, `tests/test_meta_param_descriptions.py`,
  and the two WARN_ONCE tests in `tests/test_cleanup_round_5_6_code_shape.py`.
- **Strike spec requirements** in `tool-description-contract` for
  docstring resolution (the "Per-parameter descriptions resolved from
  the docstring", "Explicit Param or Field description wins over the
  docstring", "No new third-party dependency", and "Non-goal — Numpy /
  Sphinx / reST docstring styles" requirements).
- **README**: drop the "Param descriptions from docstrings" subsection
  added in v0.29.1.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `tool-description-contract`: remove all docstring-resolution
  requirements. The contract reverts to the v0.28 surface:
  `Annotated[T, a2kit.Param(description=...)]` and
  `pydantic.Field(description=...)` are the only ways to attach
  parameter descriptions. Docstrings remain the canonical source for
  the **tool-level** description (first non-empty line and full body)
  — that requirement is unchanged.

## Impact

- Affected code: `src/a2kit/_docstring.py` (delete),
  `src/a2kit/tool.py` (drop augment helper + call in `_stamp`),
  `src/a2kit/metadata.py` (drop `param_descriptions` field).
- Affected tests: three deletions + two removed assertions.
- Breaking for any caller that read `meta.param_descriptions` (added
  one release ago in v0.29.0; no known external consumers — a2web's
  own usage was the use-case driver, never shipped).
- Public API: tool authors who relied on docstring-pull for parameter
  descriptions must add explicit `Annotated[T, a2kit.Param(...)]` or
  `pydantic.Field(...)`. CHANGELOG flags this as a v0.30.0 breaking
  removal.
