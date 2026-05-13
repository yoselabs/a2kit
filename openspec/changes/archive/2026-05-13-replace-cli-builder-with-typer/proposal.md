# Replace cli/builder.py with Typer

## Why

The spike `spike-typer-cli-replacement` (archived
`2026-05-13-spike-typer-cli-replacement`) answered all seven
sub-questions PASS and recorded a binding decision to **proceed**.
The decision rests on code-backed evidence: Annotated-Field-to-Option
adapter at ~10 LOC, JSON-string body UX as a documented divergence,
in-callback `typer.echo(format_response(...).data)` composes cleanly,
`__signature__`-synthesized connection wrapper works, cold-start
delta within noise (~5% on a ~1.3s baseline), `pretty_exceptions_enable=False`
keeps the enricher path intact, and the streaming_logger rewrite
shows tool-author surface is unchanged.

`src/a2kit/packages/cli/builder.py` is the largest single
hand-rolled reflection module in the project (~350 LOC). Typer
absorbs the bulk of its responsibilities natively. This change
swaps the implementation seam from "hand-built `click.Option` per
parameter" to "Typer reads type hints and we wire a thin adapter
on top". Net delta: roughly **-350 +100 LOC** across
`builder.py` plus a small `_field_to_typer.py` helper.

Tool-author surface is unchanged. Only the CLI builder internals
move. The MCP path is untouched.

## What Changes

1. **Replace `src/a2kit/packages/cli/builder.py`** with a
   Typer-based implementation (~70-100 LOC target).
2. **Move `typer>=0.25,<1` from dev to runtime dependency** in
   `pyproject.toml`; refresh `uv.lock`.
3. **Add `src/a2kit/packages/cli/_field_to_typer.py`** (~30 LOC)
   that reads `Annotated[T, pydantic.Field(...)]` and synthesizes
   the matching `typer.Option(...)` (description → `--help`,
   default → option default, etc.).
4. **Format-routing wrapper**: invoke
   `format_response(value, format_hint=descriptor.format_hint).data`
   from inside the command callback (or via Typer's
   `result_callback`). Single-echo, no double-encoding.
5. **Connection synthesis**: build a wrapper function whose
   `__signature__` / `__annotations__` carry an extra
   `connection: str` parameter before passing to Typer. Wrapper
   strips `connection` from kwargs before calling the underlying
   tool. (Spike Q4 confirmed.)
6. **Body-model CLI UX divergence**: tools whose kwarg is a
   Pydantic `BaseModel` get a single `--<name> '<json>'` flag on
   the CLI (JSON-string form), decoded inside the callback via
   `Model.model_validate_json`. The MCP wire shape is unchanged
   (structured object). Document as a CLI-only breaking-shape
   change in `CHANGELOG.md`. In-repo blast radius: **zero
   tools currently take `body: BaseModel`** (audit below).
7. **Exception pipeline**: wrap the tool fn with the existing
   enricher pattern BEFORE handing it to Typer; set
   `Typer(pretty_exceptions_enable=False)` to suppress Rich
   tracebacks and keep Click-style usage errors clean.
8. **Verify and delete `src/a2kit/packages/cli/schemas.py`**
   if its surface (pure-python schema gen + `schema` Click
   command) is fully replaceable through Typer + existing helpers.
   Mark as "verify before delete"; if Typer's schema gen does
   not cover `compute_schema`'s callers (testing snapshots,
   `--schema` flag, MCP path), keep `schemas.py` and document
   why in the module docstring.

## Capabilities

### MODIFIED Capabilities

- `verb-decorators` — CLI-side implementation seam shifts from
  hand-built Click commands to a Typer adapter. Tool-author
  contract (`@a2kit.read` / `@a2kit.write` / `@a2kit.tool` /
  `@a2kit.list_`) is unchanged. Spec scenario added documenting
  that `Surface.CLI`-mounted tools resolve through the Typer
  adapter.
- `tool-description-contract` — CLI body-model UX shifts from
  flattened per-field flags to a single `--<name> '<json>'`
  flag. MCP nested-object shape unchanged. Scenario added.

`cli-response-encoding` is unaffected: `format_response` remains
the single format router, only its invocation site moves from a
hand-built Click callback to a Typer callback / `result_callback`.

## Impact

- **Affected code**:
  - `src/a2kit/packages/cli/builder.py` — rewritten (~350 → ~100 LOC).
  - `src/a2kit/packages/cli/_field_to_typer.py` — new (~30 LOC).
  - `src/a2kit/packages/cli/schemas.py` — verified and likely
    deleted (callers folded into builder or kept if MCP path
    still needs `compute_schema`).
  - `pyproject.toml` — `typer>=0.25,<1` moves to `dependencies`.
  - `uv.lock` — refreshed.
  - Tests under `tests/packages/cli/` — updated for the new
    CLI shape (option help text, body-model JSON flag, error
    messages from Typer vs hand-built `UsageError`).
  - `CHANGELOG.md` — breaking CLI behavior note.
  - `README.md` — body-model CLI shape note if examples ship
    that pattern.
- **APIs**: tool-author surface unchanged. CLI option help text
  and error message format may shift slightly (Typer wording).
- **Dependencies**: `typer>=0.25,<1` added as a runtime
  dependency. Transitive Typer imports add ~70ms cold-start
  per Q5 measurement (within the spike's 10% budget on the
  measured baseline).
- **Risk**:
  - (a) Typer 1.0 ships breaking changes during the release
    window — bounded with `<1` pin; revisit on Typer 1.0.
  - (b) Hidden CLI behaviors the current builder supports that
    the spike's seven sub-questions did not exercise — mitigate
    by porting the existing `tests/packages/cli/` suite green
    before merging.
  - (c) Cold-start regression from Typer's transitive imports —
    measured within noise on the spike baseline, but `uv run`
    variance dominates; re-measure on a clean Python interpreter
    before claiming no regression.
- **Migration**: zero tool-author migration. CLI users who hand-craft
  flags for a `body: BaseModel` argument switch to JSON-string form.
  Audit:
  ```
  grep -rEn "def [a-z_]+\([^)]*\*,[^)]*:\s*[A-Z][A-Za-z]*Body"
  ```
  returns **no matches** in `src/`, `examples/`, or `tests/`. The
  spike's mention of `tracker.bulk_import_tasks` was imprecise:
  that tool takes `titles: list[str]`, not a BaseModel body. The
  divergence cost is therefore forward-only — a guard for future
  authors, not a migration for current ones.
- **Release**: post-v0.31.0. Target version TBD (likely v0.32.0,
  but does not bundle with the v0.31.0 release set).
