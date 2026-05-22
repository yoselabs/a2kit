## Why

The `consumer-aware-format-routing` change shipped green, but a follow-up
`/simplify` review surfaced loose ends: a dead code path, a per-call
recompute, a stringly-typed field forced by an import cycle, and new code
that violates the existing single-line-docstring rule. None block
correctness, but left alone they accrete as drift. This change closes them
while the context is fresh.

## What Changes

- **Remove the dead `toon` path.** `format_response`'s `format_hint="toon"`
  `ValueError` guard is unreachable: `FormatHint` (`auto|json|tsv|page-tsv`)
  excludes `toon`, so no type-checked caller can reach it. Delete the guard,
  its docstring paragraph, and the four tests that exist only to exercise it.
  No typed caller is affected; the `FormatHint` Literal already forbids the
  value.
- **Cache the `execute` stub/registry derivation.**
  `A2kitCodeMode._make_execute_tool` rebuilds the tool catalog → monty stubs
  → dataclass registry on every `execute` call, though the result is
  identical for a fixed catalog. Memoize it, keyed on the resolved
  tool-name set so a `ctx`-varying catalog still re-derives correctly.
- **Break the formatter import cycle; type the format field.** `FormatName`
  and `FormatHint` live in `formatter/__init__.py`, which submodules cannot
  import from without a cycle — so `Rendered.format` and `Response.format`
  are bare `str` with a `# "json" | "tsv"` comment. Extract a leaf
  `formatter/formats.py` (zero intra-package imports) as the type home and
  type both fields as `FormatName`.
- **Enforce the no-cycle rule.** Add a lint rule (and a
  `module-layout-discipline` requirement): a submodule SHALL NOT import from
  its own package's `__init__`. This is the durable fix for the class of
  smell above.
- **Trim verbose docstrings.** Bring the `consumer-aware-format-routing`
  code into compliance with the *existing* `module-layout-discipline`
  requirement ("module-level docstring at most one line, or absent").
  Affects `formatter/render.py`, `formatter/__init__.py`, `codemode/*`,
  `mcp/format_routing.py`, `mcp/_wrappers.py`, `cli/_serve.py`.
- **Strike stale `toon` from the format-routing specs.**
  `cli-response-encoding` still mandates a `toon` `ValueError` and describes
  a "JSON or TOON encoder"; `type-driven-format-routing` still lists `toon`
  as an accepted `format_hint` value — both contradict the shipped
  `FormatHint` Literal (`auto|json|tsv|page-tsv`). Correct them to the live
  `json` / `tsv` / `page-tsv` vocabulary so the contract stops lying.
- **Assessed, no action** (rationale recorded in design.md): the one-line
  `_is_basemodel` duplication across three packages, the `render` /
  `render_plain` dispatch overlap, and the `_to_plain` cross-package
  similarity. Each is below the abstraction threshold or spans genuinely
  different I/O domains; consolidating would add coupling, not remove it.

## Capabilities

### New Capabilities

(none — this is a cleanup change)

### Modified Capabilities

- `module-layout-discipline`: new requirement — a submodule must not import
  from its own package's `__init__.py` (import-cycle prevention), enforced
  by a new static lint rule.
- `cli-response-encoding`: drop `TOON` from the `format_response` encoding
  contract, including the requirement that `format_hint="toon"` raises
  `ValueError` — the supported wire vocabulary is `json` / `tsv` /
  `page-tsv`.
- `type-driven-format-routing`: drop `toon` from the accepted `format_hint`
  values and the stale `toon_or_json` "deprecated but exported" note.

## Impact

- **Code**: `formatter/__init__.py`, `formatter/render.py`,
  `formatter/response.py`, new `formatter/formats.py`;
  `codemode/__init__.py`; `mcp/format_routing.py`, `mcp/_wrappers.py`,
  `cli/_serve.py` (docstring trims); `packages/lint/` (new rule +
  registration).
- **Tests**: four `toon` tests removed; `test_response.py`'s `toon` usage
  updated for the typed `format` field; new tests for the cycle lint rule,
  the typed `format` field, and the `execute` caching.
- **Specs**: `module-layout-discipline`, `cli-response-encoding`, and
  `type-driven-format-routing` deltas.
- **No API change** for type-checked callers; no dependency change.
  Docstring trims are non-functional.
- **Out of scope**: stale `TOON` references in `thin-core-surface` (the
  CLI `--format` flag enum, the `--schema` default, and the retired
  auto-heuristic description) — entangled with deeper pre-existing drift;
  flagged in design.md for a separate spec-hygiene pass.
