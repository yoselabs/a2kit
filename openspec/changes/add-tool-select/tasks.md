## 1. Selector package

- [x] 1.1 Create `src/a2kit/packages/select/__init__.py` with `compile_selector`, `Selector`, `SelectorError`. Stdlib-only, ~50 LOC total.
- [x] 1.2 Implement parser: `category=values` form, comma-separated values, `!` negation prefix, whitespace stripping, reserved-char rejection.
- [x] 1.3 Implement `Selector.matches(descriptor)` per category: `verb` (string equality), `name` (`fnmatch.fnmatchcase`), `surface` (membership in `descriptor.expose` tuple).
- [x] 1.4 Reject `surface=` values outside `{"mcp", "api"}` with `SelectorError`.
- [x] 1.5 Empty include set passes vacuously; exclude check always runs.

## 2. Parser + evaluator tests

- [x] 2.1 `tests/packages/select/test_select.py` — parser tests (happy path per category, missing `=`, unknown category, empty value, surface= out-of-set, negation-only, reserved-char-in-value). *(Merged into one `test_select.py` rather than split.)*
- [x] 2.2 `tests/packages/select/test_select.py` — evaluator tests (verb equality, name fnmatch case-sensitive, surface membership, AND across multiple selectors via `build(select=[...])`).

## 3. App.build integration

- [x] 3.1 Update `App.build(...)` signature to accept `select: list[str] | None = None`. Compile each expression; raise `SelectorError` at compile (before App work).
- [x] 3.2 Apply ANDed selectors to filter `app._tools`, `app._api_routes`, `app._mcp_features`. For `surface=` selectors, reduce per-tool `expose` tuples; drop the tool only if `expose` becomes empty.
- [x] 3.3 Freeze filtered registries on `AppRuntime`. Confirm dispatch path never invokes `Selector`.

## 4. CLI wiring

- [x] 4.1 Add `--select` Click option (`multiple=True`) to the `serve` callback. *(Used Click — the existing `serve` command is Click-based; Typer is only for the top-level CLI builder.)*
- [x] 4.2 Catch `SelectorError` at CLI entry: ``click.UsageError`` is raised with the parser's message; Click prints it and exits with status 2.
- [x] 4.3 Pass the collected list through to `build(app, select=select_list)`.

## 5. Integration tests

- [x] 5.1 `tests/packages/select/test_select_serve_integration.py::test_surface_mcp_select_skips_fastapi_mount` and `test_surface_api_select_skips_fastmcp_mount` — surface filter narrows the parent mount table.
- [x] 5.2 *(Same file)* — surface-only parameterised across `surface=mcp` / `surface=api`; the unselected substrate's mount path is absent from the parent.
- [x] 5.3 `test_filter_to_empty_raises_value_error` — filter that drops everything triggers `build_parent_app`'s `ValueError("no surfaces have registrations to expose")`. *(Spec said `ConfigError`; reused stdlib `ValueError` per the same divergence noted in add-multi-surface task 5.3.)*

## 6. Documentation

- [ ] 6.1 Write `docs/SELECT.md` with the DSL reference and 5+ worked examples. *(Pending — DSL reference lives in the `--select` Click help text and the `tool-selection` spec; standalone doc deferred to a follow-up.)*
- [x] 6.2 Update CLI `--help` text for `--select` — covers syntax, both example forms (`surface=mcp`, `name=fetch_*,!internal_*`), and AND semantics across repeated flags.

## 7. Validation

- [x] 7.1 `openspec validate add-tool-select --strict` passes.
- [x] 7.2 `make lint` green; `make test` green.
- [x] 7.3 Cold-start invariant: `import a2kit` does not load `packages/select` (lazy under serve).
