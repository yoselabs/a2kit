# Design — Replace cli/builder.py with Typer

## Context

The spike `spike-typer-cli-replacement`
(`openspec/changes/archive/2026-05-13-spike-typer-cli-replacement/design.md`)
ran all seven sub-questions and recorded PASS on each:

- Q1 (Field-description-as-`--help`): PASS with ~10 LOC adapter.
- Q2 (Body-model handling): PASS with documented JSON-string divergence.
- Q3 (Format routing): PASS — in-callback `typer.echo`, no `result_callback` required.
- Q4 (Connection synthesis): PASS — `__signature__`-wrapped function.
- Q5 (Cold-start): PASS — ~70ms typer import, ~5% on ~1.3s baseline.
- Q6 (Exception pipeline): PASS — enricher wraps before Typer sees the call;
  `pretty_exceptions_enable=False` suppresses Rich tracebacks.
- Q7 (Tool-author ergonomics): PASS — `streaming_logger` re-runs unchanged
  through a ~70 LOC adapter.

Decision: **proceed**. This document captures the implementation-level
decisions for the follow-up.

## Goals

- Replace `src/a2kit/packages/cli/builder.py` with a Typer-driven
  implementation, retaining every observable behavior the current
  CLI surface has except the body-model UX (documented below).
- Keep the tool-author surface (`@a2kit.read` / `@a2kit.write` /
  `@a2kit.tool` / `@a2kit.list_`) byte-identical.
- Net LOC reduction in the `cli/` package of roughly 250 lines.

## Non-goals

- No change to the MCP path. Only `cli/builder.py` (and the
  optional deletion of `cli/schemas.py`) is in scope.
- No change to `a2kit.packages.formatter`. The format router is
  invoked from a different site; its internals are unchanged.
- No change to tool-author API. Authors do not import Typer.
- Not a v0.32.0 marker. Release version TBD; does not bundle with
  the v0.31.0 release set.

## Decisions

### D1 — Typer as runtime dependency

Move `typer>=0.25,<1` from dev to runtime `dependencies` in
`pyproject.toml`. Rationale: required by the CLI mode, which is a
first-class surface of `a2kit`. The `<1` upper pin guards against
the unreleased Typer 1.0 breaking-change window. Click is already
a runtime dep; Typer is built on Click.

### D2 — `_field_to_typer.py` adapter location and shape

New module `src/a2kit/packages/cli/_field_to_typer.py`. Internal
(underscore-prefixed) helper consumed only by `builder.py`. Shape:

- Single public function, roughly:
  ```python
  def field_to_typer_option(name: str, annotation: Any, default: Any) -> tuple[Any, Any]:
      """Return (rewritten_annotation, default_with_typer_Option_metadata)."""
  ```
- Reads `Annotated[T, pydantic.FieldInfo]` metadata. If `FieldInfo.description`
  is set, rewrites to `Annotated[T, typer.Option(help=..., default=...)]`.
- ~30 LOC total. No Typer leakage above this module.

Rationale: keeps the Annotated rewrite isolated, testable in
isolation, and replaceable if Typer ever gains native pydantic-Field
support.

### D3 — Body-model UX: JSON string

Tools with a `body: SomeBaseModel` parameter receive a single CLI
flag `--body '<json>'`. The callback decodes via
`SomeBaseModel.model_validate_json(value)`. Explicitly chosen over
the alternative (walk the BaseModel and synthesize one option per
field).

Rationale:
- Aligns CLI with MCP wire shape (both transports take a structured
  object; only the encoding differs).
- Removes ~150 LOC of pydantic-model flattening from the builder.
- Accepts a small CLI UX regression for body-model tools — but
  audit shows **zero in-repo tools currently use this shape**
  (the spike's mention of `tracker.bulk_import_tasks` was
  imprecise; that tool takes `titles: list[str]`, not a BaseModel
  body).
- Authors who want flattened-flag UX on the CLI can decompose the
  body into individual kwargs in the tool signature, which is the
  shape every existing in-repo tool already uses.

Trade-off accepted: future authors who write `body: SomeBaseModel`
get JSON-string CLI UX, not flattened flags. Documented in
`tool-description-contract` spec delta.

### D4 — `schemas.py`: split into a new core module and delete

`src/a2kit/packages/cli/schemas.py` exposes two things:
- `compute_schema(fn, container)` — pure-Python schema dict.
  Pydantic + a2kit internals only; no `click`, no `fastmcp`.
  Consumed by:
  - `src/a2kit/packages/cli/builder.py` (line 295) — the
    `--schema` per-tool flag.
  - `src/a2kit/packages/testing/snapshots.py` — snapshot
    assertions in user tests.
  - `src/a2kit/testing.py` — public re-export
    `a2kit.testing.compute_schema`.
- `build_schema_command(app)` — the top-level `<app> schema [tool]`
  Click command. Pure CLI wiring.

Resolution: `compute_schema` is **transport-neutral schema
introspection** — wrong neighborhood in `cli/`. Move to a new
core module `src/a2kit/schema.py`, lazy-imported via
`_LAZY_MODULES` in `__init__.py` (same pattern as `a2kit.lifespan`
landed by `lifespan-over-lifecycle-hooks`). Delete
`src/a2kit/packages/cli/schemas.py` entirely.

After migration:

```
src/a2kit/
  schema.py            ← compute_schema (NEW, lazy-imported)
  __init__.py          ← _LAZY_MODULES entry for `schema`
  packages/
    cli/
      builder.py       ← Typer; imports compute_schema from a2kit.schema
                         for the `schema` subcommand (replaces
                         build_schema_command's Click wiring)
      # schemas.py     ← DELETED
    testing/
      snapshots.py     ← imports compute_schema from a2kit.schema
  testing.py           ← re-exports compute_schema from a2kit.schema
```

Rejected alternatives:
- `packages/testing/schema.py` — wrong dependency direction;
  production CLI depending on testing-tooling smells.
- `packages/mcp/schema.py` — misleading. FastMCP generates its
  own schema natively; a2kit's `compute_schema` exists because
  FastMCP doesn't see the wire-scope-stripped form. Tying it
  to MCP confuses the contract.
- Inline into each caller — duplication. Hard pass.

Public surface preserved: `a2kit.testing.compute_schema` continues
to import the function, just from the new core location. No
downstream caller signature change.

### D5 — Cold-start preservation

Keep Typer imported lazily inside `build_full_cli` and the
per-command factory chain. `import a2kit` must NOT pull `typer`.
The existing LazyGroup pattern in `builder.py` already enforces
this discipline for `serve` (fastmcp). Port the same discipline
to the Typer rewrite. Concretely:

- `from typer import Typer, Option` lives inside the function body
  of `build_full_cli`, NOT at module top.
- Typer's `pretty_exceptions_enable=False` is set at app
  construction.

If the post-merge cold-start measurement regresses beyond noise,
investigate `shellingham` and `typer.completion` — both are
imported by `typer.main`. Worst case, a `typer.main` import-time
patch is acceptable but ugly.

### D6 — Exception pipeline

Keep the existing `_wrap_with_enricher` pattern. The wrapped fn
is what Typer sees, so enrichers run before any Typer / Click
catch. Set `Typer(pretty_exceptions_enable=False)` at the app
construction site. UsageError-class problems (missing required
option, bad type) continue to surface as Click-style messages —
those never reach the enricher and don't need to.

## Risks

- **Typer 1.0 breaking-change window.** `typer>=0.25,<1` upper-pin
  guards. Revisit the pin on Typer 1.0 release.
- **Hidden CLI behaviors not exercised by the spike.** The spike
  covered Q1-Q7 on a representative router. The current `builder.py`
  has additional behaviors (LazyGroup, markdown stripping for
  long-help, the `--schema` per-tool flag, `--format` choice
  routing, `--no-reports` / `--no-events` top-level flags,
  `<app> health` shorthand). Each must be re-derived under Typer.
  Mitigation: port the existing `tests/packages/cli/` suite green
  before merging; no behavior delta beyond D3 is acceptable.
- **Cold-start regression.** Measured within noise on the spike
  baseline. `uv run` variance dominates; re-measure under
  `python -X importtime` on a clean interpreter before claiming
  no regression.

## Migration

- **Tool authors**: nothing to do.
- **CLI users**: if a tool exposes `body: BaseModel` as a flag,
  switch to JSON-string form (`--body '{...}'`). Audit: zero
  in-repo tools match this shape. Forward-only guard.
- **CHANGELOG**: breaking-shape note under the release that
  ships this change.

## Open questions

- **Target release version.** Post-v0.31.0 is decided; the
  specific number (v0.32.0?) is TBD.

## Resolved questions

- **Two-mode body UX?** RESOLVED: single-mode JSON-string only
  (D3). The flattened-flags path is rejected, not deferred —
  keeping it costs the ~150 LOC the spike was supposed to save
  and asks every tool author to pick a mode. Authors who want
  flat-flag CLI ergonomics on a structured input write explicit
  signature params (`title: str, priority: int`) rather than
  `body: TaskCreate`. Same surface, no per-tool mode flag.
- **`compute_schema` home?** RESOLVED: new core module
  `src/a2kit/schema.py`, lazy-imported (D4). CLI and testing
  both depend on core. Public re-export at
  `a2kit.testing.compute_schema` preserved.
