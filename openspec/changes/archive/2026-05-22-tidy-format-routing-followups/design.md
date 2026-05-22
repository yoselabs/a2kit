## Context

`consumer-aware-format-routing` shipped green. A `/simplify` review then
flagged six follow-ups. Three warrant code changes, two are spec-hygiene,
and three were assessed and deliberately left alone. This design records
the decisions so the apply step is mechanical.

Current state worth knowing:

- `FormatHint = Literal["auto","json","tsv","page-tsv"]` and
  `FormatName = Literal["json","tsv"]` are defined in
  `formatter/__init__.py`. `FormatName` has **zero consumers** — it is only
  re-exported. `Rendered.format` and `Response.format` are bare `str`
  (the latter carries a `# "json" | "tsv"` comment) because a submodule
  importing `FormatName` from `__init__.py` would form an import cycle.
- `A2kitCodeMode._make_execute_tool`'s `execute` closure rebuilds the tool
  catalog → monty stubs → dataclass registry on every invocation.
- `cli-response-encoding` mandates `format_hint="toon"` raise `ValueError`
  and has a "TOON is unsupported" scenario; `type-driven-format-routing`
  lists `toon` among accepted `format_hint` values. Both contradict the
  shipped `FormatHint` Literal, which has no `toon`.
- `module-layout-discipline` already requires module docstrings be "at most
  one line, or absent" — the new `consumer-aware-format-routing` code
  (16-line module docstring in `render.py`, multi-paragraph function
  docstrings) violates it. No `fastmcp`-style import rule exists for
  intra-package `__init__` cycles.

## Goals / Non-Goals

**Goals:**

- Delete the unreachable `toon` `ValueError` path and align the two specs
  that still describe `toon` as live.
- Eliminate the per-`execute`-call catalog/stubs/registry recompute.
- Break the `formatter` import cycle with a leaf type module so
  `Rendered.format` / `Response.format` can be `FormatName`-typed, and add
  a lint rule that prevents the cycle class from recurring.
- Bring the `consumer-aware-format-routing` code into compliance with the
  existing single-line-docstring rule.

**Non-Goals:**

- Repo-wide docstring rewrite — only the `consumer-aware-format-routing`
  surface is in scope.
- `thin-core-surface` `toon` cleanup — its `toon` references are tangled
  with deeper drift (the retired `--format=auto` TSV/TOON/JSON heuristic
  description, the `--schema` default). A separate spec-hygiene change.
- Consolidating `_is_basemodel`, `render`/`render_plain`, or `_to_plain`
  (see Decisions — assessed, no action).

## Decisions

### D1 — Remove the `toon` path entirely, spec included

`toon` was dropped in v0.22; the `ValueError` was a migration aid. The
`FormatHint` Literal already forbids the value, so no type-checked caller
can reach the guard, and a guard for a type-impossible input is dead
weight. Delete the `format_response` branch, its docstring paragraph, and
the four tests that exist only to assert it (`test_format_toon_raises`,
`test_toon_format_no_longer_offered`, `test_toon_hint_raises`,
`test_format_hint_toon_raises`).

The two specs that still describe `toon` are corrected to match shipped
reality (`cli-response-encoding`, `type-driven-format-routing`). The
"tests exist" fact does not justify keeping the behavior — the tests are
removed *because* the behavior is being removed.

**Alternative considered:** keep the guard as a friendly runtime error for
untyped callers. Rejected — a permanent shim for a value the type system
already rejects is exactly the backward-compat cruft a2kit doctrine bans.

### D2 — Cache the `execute` derivation on the transform instance

`get_tool_catalog` can vary with `ctx` (per-request middleware filtering),
so the catalog cannot be frozen at `__init__`. But for a given resolved
tool-name set the stubs and registry are identical. Memoize on the
`A2kitCodeMode` instance: a dict keyed by the `tuple(sorted(tool names))`
of the resolved catalog → `(stubs, registry)`. `dataclass_mirror` is
already globally cached, so the cache mainly elides the `generate_stubs`
string build and the `collect_models` annotation walk.

**Alternative considered:** build once at `__init__`. Rejected — ignores
`ctx`-varying catalogs. **Alternative:** no cache. Rejected — the user
asked for it and the keyed cache is small and correct.

### D3 — Leaf module `formatter/formats.py` for the format vocabulary

Move `FormatHint` and `FormatName` into a new `formatter/formats.py` that
imports nothing from within `formatter`. `__init__.py` re-exports both (no
public-API change). `render.py` imports `FormatName` from `.formats` and
types `Rendered.format`; `response.py` imports it and types
`Response.format`.

`formats.py` satisfies `module-layout-discipline` ("name equals concept" —
it is the format-name vocabulary; public name, no underscore).

**Alternatives considered:** put the aliases in `response.py` — rejected,
`response.py` is not a pure leaf and the format vocabulary is not a
"response" concept. Put them in `inference.py` — rejected, `inference.py`
is type-*introspection* logic, a different concept.

### D4 — New lint rule: no submodule imports from its own package `__init__`

Add a static rule (`A2K-PKG-INIT-IMPORT`) to `packages/lint/rules/`. It
fires when a file `src/a2kit/<pkg>/<sub>.py` (not the `__init__.py`
itself) imports from its own package root — either the absolute form
`from a2kit.<...>.<pkg> import ...` or the relative `from . import ...`.
That is exactly the latent-cycle pattern D3 fixes.

A real cycle already crashes at import; the rule catches the cases that
work today only by import-ordering luck. The apply step runs the rule
across `src/` first and fixes any pre-existing hits (the fix is always:
import from the defining submodule directly). The rule is registered in
`ALL_RULES` and surfaces under `a2kit lint static`.

**Alternative considered:** fold it into `A2K-IMPORT-DISCIPLINE`. Rejected
— that rule is `fastmcp`-specific; one rule, one concern.

### D5 — Trim docstrings to the existing rule

`module-layout-discipline` already mandates "module-level docstring at
most one line, or absent" and "comments document only non-obvious why".
Bring `render.py`, `formatter/__init__.py`, `codemode/{__init__,marshal,
runtime,stubs}.py`, `mcp/format_routing.py`, `mcp/_wrappers.py`,
`cli/_serve.py` into compliance: collapse module docstrings to one line,
shorten multi-paragraph function docstrings to a concise statement. Keep
genuine non-obvious WHY (e.g. why a fallback exists, why an import is
function-local). No spec change — this enforces an existing requirement.

### D6 — Assessed, no action (with rationale)

- **`_is_basemodel` duplicated** in `formatter/inference.py`,
  `codemode/marshal.py`, `cli/builder.py`. It is one line
  (`isinstance(tp, type) and issubclass(tp, BaseModel)`), stdlib-only.
  A shared home means three packages coupling to a util for a one-liner.
  Doctrine: three similar lines beat a premature abstraction. **Keep.**
- **`render` vs `render_plain` dispatch overlap.** `render` consumes typed
  objects (`BaseModel` / `Page`) on the pre-FastMCP path; `render_plain`
  consumes post-FastMCP plain dicts and uses different encoders
  (`encode_page_tsv_dict` vs `encode_page_tsv`). Unifying needs a
  kind→encoder-pair indirection more abstract than the four short branches
  it would remove. **Keep separate.**
- **`_to_plain` cross-package similarity** with the LDD normalizer and
  `schema.py`'s `asdict` use. Three serialization contexts with subtle
  differences (`mode="json"` vs not, leaf definition). A shared helper
  risks silent behavior divergence across all three. **Keep.**

## Risks / Trade-offs

- **The new lint rule fires on pre-existing code** → apply runs it across
  `src/` before wiring it into `make lint`; each hit is fixed (import from
  the submodule) or, only if genuinely unavoidable, allow-listed with a
  `# why:` note. Expected hit count is low — true cycles already crash.
- **`Response.format: FormatName` narrows a public dataclass field** →
  only `test_response.py` constructs `Response` with a non-`FormatName`
  string (`format="toon"`); it is updated in the same change.
- **Docstring trimming could drop useful WHY** → trims target WHAT-
  restatement and multi-paragraph prose only; non-obvious WHY lines are
  preserved verbatim.
- **Spec deltas must match existing requirement headers exactly** →
  `openspec validate --strict` is run after writing each delta.

## Open Questions

None blocking. For the deferred `thin-core-surface` pass: confirm what
`--schema` printing defaults to now that TOON is gone (almost certainly
JSON) — out of scope here.
