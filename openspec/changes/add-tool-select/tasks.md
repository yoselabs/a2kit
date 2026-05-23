## 1. Selector package

- [ ] 1.1 Create `src/a2kit/packages/select/__init__.py` with `compile_selector`, `Selector`, `SelectorError`. Stdlib-only, ~50 LOC total.
- [ ] 1.2 Implement parser: `category=values` form, comma-separated values, `!` negation prefix, whitespace stripping, reserved-char rejection.
- [ ] 1.3 Implement `Selector.matches(descriptor)` per category: `verb` (string equality), `name` (`fnmatch.fnmatchcase`), `surface` (membership in `descriptor.expose` tuple).
- [ ] 1.4 Reject `surface=` values outside `{"mcp", "api"}` with `SelectorError`.
- [ ] 1.5 Empty include set passes vacuously; exclude check always runs.

## 2. Parser + evaluator tests

- [ ] 2.1 `tests/packages/select/test_compile.py` — happy path per category, parser errors (missing `=`, unknown category, empty value, surface= out-of-set, negation-only), negation semantics.
- [ ] 2.2 `tests/packages/select/test_evaluator.py` — verb match, name glob (case-sensitive), surface filter reducing `expose`, AND across multiple selectors.

## 3. App.build integration

- [ ] 3.1 Update `App.build(...)` signature to accept `select: list[str] | None = None`. Compile each expression; raise `SelectorError` at compile (before App work).
- [ ] 3.2 Apply ANDed selectors to filter `app._tools`, `app._api_routes`, `app._mcp_features`. For `surface=` selectors, reduce per-tool `expose` tuples; drop the tool only if `expose` becomes empty.
- [ ] 3.3 Freeze filtered registries on `AppRuntime`. Confirm dispatch path never invokes `Selector`.

## 4. CLI wiring

- [ ] 4.1 Add `--select` typer option (repeatable `list[str]`) to the `serve` callback. Help text references `docs/SELECT.md`.
- [ ] 4.2 Catch `SelectorError` at CLI entry: one-line stderr message naming the offending fragment; exit code 2.
- [ ] 4.3 Pass the collected list through to `build(app, select=select_list)`.

## 5. Integration tests

- [ ] 5.1 `tests/packages/select/test_integration.py::test_read_only_mode` — full multiplex serve with `--select 'verb=read,list'`; assert MCP `tools/list` and FastAPI routes contain only read/list tools.
- [ ] 5.2 `tests/packages/select/test_integration.py::test_surface_only` — parameterized over `surface=mcp` and `surface=api`; assert the unselected substrate is unmounted (Starlette parent returns 404 for the absent prefix).
- [ ] 5.3 `tests/packages/select/test_integration.py::test_filter_empties_raises` — filter that removes everything raises `ConfigError` with "after selector filter" in the message.

## 6. Documentation

- [ ] 6.1 Write `docs/SELECT.md` with the DSL reference and 5+ worked examples (read-only, specific tools by glob, surface-only, combinations with multiple flags).
- [ ] 6.2 Update CLI `--help` text for `--select` to point at the doc and include the canonical "MCP-only" pattern (`--select 'surface=mcp'`).

## 7. Validation

- [ ] 7.1 `openspec validate add-tool-select --strict` passes.
- [ ] 7.2 `make lint` green; `make test` green.
- [ ] 7.3 Cold-start invariant: `import a2kit` does not load `packages/select` (lazy under serve).
