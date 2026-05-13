# Tasks — Replace cli/builder.py with Typer

## 1. Runtime dependency wiring

- [ ] 1.1 Move `typer>=0.25,<1` from dev `optional-dependencies`
      (or wherever the spike placed it) into the top-level
      `[project].dependencies` block of `pyproject.toml`.
- [ ] 1.2 Run `uv lock` to refresh `uv.lock`.
- [ ] 1.3 Add a top-level import test: `python -c "import a2kit"`
      must NOT trigger `import typer` (verified via
      `python -X importtime`). Codify in `tests/test_cold_start.py`
      or equivalent.

## 2. Annotated-Field-to-Typer adapter

- [ ] 2.1 Create `src/a2kit/packages/cli/_field_to_typer.py`
      (~30 LOC). Single public helper that reads
      `Annotated[T, pydantic.FieldInfo]` and produces the rewritten
      annotation with `typer.Option(help=..., default=...)` metadata.
- [ ] 2.2 Unit-test the adapter standalone:
      `tests/packages/cli/test_field_to_typer.py`.

## 3. Rewrite `builder.py`

- [ ] 3.1 Replace `src/a2kit/packages/cli/builder.py` body with a
      Typer-based implementation (~70-100 LOC target).
- [ ] 3.2 Preserve `LazyGroup`-equivalent behavior for `serve`
      (Typer's `add_typer` with a callback factory, or a Typer
      app whose `serve` subcommand triggers fastmcp import only
      on invocation).
- [ ] 3.3 Preserve top-level `--no-reports` / `--no-events` flags.
- [ ] 3.4 Preserve `<app> health` shorthand when `_health.enabled`.
- [ ] 3.5 Preserve docstring-to-help mapping (PEP 257 dedent +
      markdown strip for CLI long-help).
- [ ] 3.6 Build per-tool commands via a `make_typer_command(app, fn, router)`
      adapter (the spike prototype shape).

## 4. Format routing wiring

- [ ] 4.1 Inside each Typer command callback, invoke
      `format_response(value, format_hint=descriptor.format_hint).data`
      and emit via `typer.echo` exactly once.
- [ ] 4.2 Preserve the per-tool `--format {auto,json,tsv,page-tsv}`
      option and `--schema` flag wiring.
- [ ] 4.3 No double-encoding: command body returns `None` after
      explicit echo (matches the spike Q3 finding).

## 5. Exception pipeline wiring

- [ ] 5.1 Set `pretty_exceptions_enable=False` on the top-level
      Typer app.
- [ ] 5.2 Wrap the tool fn with `_wrap_with_enricher` (existing
      helper) BEFORE handing to `make_typer_command`, so enrichers
      see the exception before Typer.
- [ ] 5.3 Verify Click-style UsageError messages still appear for
      missing required options and bad types.

## 6. Connection synthesis

- [ ] 6.1 In `make_typer_command`, when `wire_input_params` reports
      `connection` is needed, build a wrapper function with
      `__signature__` / `__annotations__` carrying an extra
      `connection: str` parameter.
- [ ] 6.2 The wrapper strips `connection` from kwargs before
      calling the underlying tool unless the tool itself declares
      `connection` (matches current behavior in
      `_make_tool_command`).
- [ ] 6.3 Test: a tool with no `connection` parameter still exposes
      `--connection` on the CLI; a tool that declares `connection`
      receives the value normally.

## 7. Split `schemas.py` into core module + Typer command, delete CLI file

- [ ] 7.1 Create `src/a2kit/schema.py` containing only
      `compute_schema(fn, container)` (and its private helpers
      `_resolved_hints`, `_annotation_to_field`, `_input_schema`,
      `_output_schema`). No `click` import. Module docstring:
      "Transport-neutral tool schema introspection."
- [ ] 7.2 Add `"schema"` to `_LAZY_MODULES` in
      `src/a2kit/__init__.py` (same pattern as `lifespan` landed
      by `lifespan-over-lifecycle-hooks`). `import a2kit` MUST
      NOT pull `a2kit.schema`.
- [ ] 7.3 Update `src/a2kit/packages/testing/snapshots.py` to
      import `compute_schema` from `a2kit.schema` instead of
      `a2kit.packages.cli.schemas`.
- [ ] 7.4 Update `src/a2kit/testing.py` re-export source to
      `a2kit.schema.compute_schema`. Public surface
      `a2kit.testing.compute_schema` unchanged.
- [ ] 7.5 In the new Typer-based `builder.py`, add the
      `<app> schema [tool]` Typer subcommand. Import
      `compute_schema` from `a2kit.schema`. Replaces
      `build_schema_command`'s Click wiring entirely.
- [ ] 7.6 Replace the per-tool `--schema` flag handler in
      `builder.py` line 295 area: import from `a2kit.schema`.
- [ ] 7.7 Delete `src/a2kit/packages/cli/schemas.py` entirely.
- [ ] 7.8 Verify with `grep -rn "from.*cli.schemas\|cli\.schemas"
      src/ tests/ examples/` — zero matches. No surviving import.
- [ ] 7.9 Verify cold-start invariant: `python -X importtime -c
      'import a2kit'` does NOT show `a2kit.schema` in the loaded
      modules tree.

## 8. Test suite update

- [ ] 8.1 Audit `tests/packages/cli/` (and any other tests that
      exercise the CLI builder). Update assertions for Typer-style
      `--help` text and error messages where they differ from
      Click-only output.
- [ ] 8.2 Add a test for the JSON-string body-model UX:
      `<app> tool --body '{"k":"v"}'` decodes correctly.
- [ ] 8.3 Add a test that confirms `pretty_exceptions_enable=False`
      effective behavior: an unenriched exception prints a plain
      message, not a Rich-styled traceback.
- [ ] 8.4 Run the full `tests/` suite green; no regression beyond
      D3 is acceptable.

## 9. Docs

- [ ] 9.1 `CHANGELOG.md`: add a breaking-shape note for body-model
      CLI users (JSON-string form). Even though the in-repo blast
      radius is zero, the change is observable for downstream
      authors.
- [ ] 9.2 `README.md`: if any example shows body-model CLI usage,
      update the example. (Audit: likely zero updates needed.)
- [ ] 9.3 Write an ADR documenting the Typer migration decision at
      `docs/adr/NNNN-typer-cli.md` (pick the next ADR number; create
      the `docs/adr/` directory if it doesn't exist). Sections:
      Context (350-LOC hand-rolled Click reflection in
      `cli/builder.py`; FastMCP-magic-ceiling audit found it the
      largest single non-orthogonal seam; spike confirmed all 7
      sub-questions PASS), Decision (replace with Typer +
      ~30-LOC `_field_to_typer.py` adapter; runtime dependency;
      JSON-string body UX divergence), Consequences (positive: ~250
      LOC net deletion, alignment with ecosystem standard, Rust/TS
      port now picks each language's CLI lib independently; negative:
      Typer dep weight, Pydantic-model body flags become a single
      JSON string), Alternatives Considered (keep builder.py: spike
      showed Typer is mature enough; argparse/cleo/cyclopts: Typer
      is the established FastAPI sibling, aligns with pydantic
      idioms; build our own thinner shim: doesn't address the
      ecosystem-standard alignment goal), Reference (spike
      design.md path; this proposal's path). Format: standard ADR
      template — Title / Status / Context / Decision / Consequences
      / Alternatives / References.

## 10. Migration audit

- [ ] 10.1 Run:
      ```
      grep -rEn "def [a-z_]+\([^)]*\*,[^)]*:\s*[A-Z][A-Za-z]*Body" \
        src/a2kit/ examples/ tests/
      ```
      Confirm zero matches (or list any matches found and update
      each).
- [ ] 10.2 Same audit for `: BaseModel` outside of model definitions:
      ```
      grep -rEn "def [a-z_]+\([^)]*\*,[^)]*:\s*[A-Z][A-Za-z]+\)" ...
      ```
      Cross-check against types that are pydantic models — those
      are the affected callers.
- [ ] 10.3 Record the audit result in the PR description.

## 11. Validate

- [ ] 11.1 Run `openspec validate replace-cli-builder-with-typer --strict`;
      iterate until clean.
- [ ] 11.2 Run the full test suite green.
- [ ] 11.3 Re-measure cold-start via `python -X importtime` on a
      clean interpreter; record the delta in the PR.
