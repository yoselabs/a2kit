# Tasks — pull parameter descriptions from the tool docstring

## 0. Prerequisites

- [x] 0.1 Baseline: `uv run pytest --no-cov` green; `make lint` green.
- [x] 0.2 Capture today's MCP schema and CLI `--help` output for one
      a2web-style router tool (`url`, `timeout` kwargs with
      `Param(description=...)` wrappers); use as a regression
      anchor to confirm explicit-`Param`-wins precedence after the
      change lands.

## 1. Library — docstring resolver

- [x] 1.1 Add `src/a2kit/_docstring.py` with a single public helper
      `extract_param_descriptions(doc: str | None) -> Mapping[str, str]`.
      Use `inspect.cleandoc` then iterate; recognise headers
      `Args:`, `Arguments:`, `Parameters:` (case-insensitive).
      Stop on the next recognised Google section header
      (`Returns:`, `Raises:`, `Yields:`, `Examples:`, `Note:`,
      `Notes:`, `Attributes:`, `See Also:`) or end of doc.
- [x] 1.2 Within the section, parse entries of shape
      `name: desc` or `name (type): desc`. Discard the `(type)`
      group. Join continuation lines (those indented further than
      the entry line) with a single space.
- [x] 1.3 Return an empty mapping on any parse anomaly — never raise.

## 2. Library — wire into `_stamp`

- [x] 2.1 In `src/a2kit/tool.py::_stamp`, after `_check_return`,
      compute `param_descriptions` by walking
      `inspect.signature(fn).parameters` and resolving each kwarg
      via the precedence rule (explicit `FieldInfo.description`
      from `Annotated[...]` → docstring entry → omit).
- [x] 2.2 Skip `self`, `*args`, `**kwargs`, and the
      `find_context_param(fn)` parameter name.
- [x] 2.3 Store the mapping on `A2KitMeta` (new field
      `param_descriptions: Mapping[str, str] = frozendict()` or
      equivalent frozen mapping).
- [x] 2.4 Confirm all four verb decorators (`tool`, `read`, `write`,
      `list_`) hit `_stamp` and therefore inherit the behaviour.

## 3. Library — schema and CLI builders consume the mapping

- [x] 3.1 In the MCP input-schema builder, before emitting each
      parameter's schema, apply
      `A2KitMeta.param_descriptions[name]` as the `description`
      when the parameter does not already have one from
      `Annotated[...]` metadata.
- [x] 3.2 In the click-option builder, do the same for the option
      help string.
- [x] 3.3 Verify nothing changes for parameters that already carry
      an `Annotated[T, Param(description=...)]` wrapper (regression
      anchor from task 0.2).

## 4. Tests

- [x] 4.1 Unit tests for `_docstring.extract_param_descriptions`:
      Args/Arguments/Parameters aliases, type-suffix discard,
      continuation joining, section termination on the next
      header, malformed input returns empty.
- [x] 4.2 Integration test: tool with docstring-only descriptions
      surfaces them in the MCP input schema (via the in-process
      test client) and in click `--help`.
- [x] 4.3 Integration test: explicit `Param(description=...)`
      overrides matching docstring entry; both forms
      (kwarg and positional shorthand) tested.
- [x] 4.4 Integration test: `Param(examples=[...])` without a
      description picks up the docstring description while
      keeping its `examples`.
- [x] 4.5 Integration test: `ctx` / `self` documented in `Args:`
      are ignored.
- [x] 4.6 Negative test: Numpy-style `Parameters\n----------\n`
      block is NOT parsed; parameters fall back to "no description".

## 5. Examples and docs

- [x] 5.1 Migrate one in-repo example (suggest `examples/tracker/`
      or `examples/streaming_logger/`) to drop redundant
      `Param(description=...)` wrappers and rely on the docstring.
      Keep one example that still uses `Param(examples=...)` to
      show the surviving use case.
- [x] 5.2 Update `README.md` / docs section that introduces
      `Annotated[T, a2kit.Param(...)]` to lead with the docstring
      style and mention `Param` as the explicit-override / extra-
      metadata escape hatch.

## 6. Validation gates

- [x] 6.1 `make lint` green.
- [x] 6.2 `uv run pytest --no-cov` green; new tests under task 4 are
      authored TDD-first (red, then green).
- [x] 6.3 `openspec validate param-docstring-pull --strict` passes.
- [x] 6.4 Manual: run the a2web router smoke (or in-repo
      equivalent) and confirm the MCP `tools/list` response carries
      the per-parameter descriptions.
