## 1. Page becomes generic pydantic model (foundation)

- [ ] 1.1 Add failing test in `tests/packages/formatter/test_response.py`: `Page[Task](items=[...], next_cursor="x")` validates; field order is `items`, `next_cursor`; bare `Page(items=[some_dict])` still constructs (back-compat).
- [ ] 1.2 Rewrite `Page` in `src/a2kit/packages/formatter/response.py` as `class Page(BaseModel, Generic[T])` with `items: list[T] = Field(default_factory=list)` and `next_cursor: str | None = None`. Drop the `@dataclass(frozen=True)` decorator.
- [ ] 1.3 Update the docstring in `response.py` to reflect the BaseModel change and reference the type-driven routing role.
- [ ] 1.4 Run the test suite — `Page` tests pass; existing callers that construct `Page(items=[...], next_cursor=None)` still work.

## 2. Type inference module (failing tests first)

- [ ] 2.1 Add `tests/packages/formatter/test_type_inference.py` with table-driven cases for every row of the `_infer_format_hint` table (scalar-only model in list → tsv; list with list field → json; nested model → json; single BaseModel → json; Page[scalar] → page-tsv; Page[non-scalar] → json; subclass of Page → same rules; bare Page → json; list[str] → json; dict → json; Any/missing → json; Union → json).
- [ ] 2.2 Add tests for `_is_dump_scalar`: `Optional[str]` → True; `Annotated[int, Field(ge=0)]` → True; `list[str]` → False; `Enum` subclass → True; `BaseModel` subclass → False.
- [ ] 2.3 Add `src/a2kit/packages/formatter/inference.py` with `_infer_format_hint`, `_is_dump_scalar`, `_model_is_scalar_only`, `_is_basemodel`. No imports from cli/runtime — formatter is a leaf.
- [ ] 2.4 Implement the table per the spec. Run the suite — all inference tests green.

## 3. TSV and page-tsv encoders (failing tests first)

- [ ] 3.1 Add `tests/packages/formatter/test_tsv_encoder.py`: header in declared field order; comma in cell does NOT quote; tab/newline/quote DOES quote; datetime renders via `model_dump(mode="json")`; list/dict cells JSON-blob'd when forced.
- [ ] 3.2 Add `tests/packages/formatter/test_page_encoder.py`: hybrid output is parseable as JSON; `_items_format == "tsv"`; items string parses back via stdlib csv; subclass extra fields (`total`) pass through; empty items emits header line only.
- [ ] 3.3 Implement `src/a2kit/packages/formatter/tsv.py::encode_tsv(rows, columns)`. Use stdlib `csv.DictWriter`, `delimiter="\t"`, `lineterminator="\n"`, `quoting=csv.QUOTE_MINIMAL`, `extrasaction="ignore"`.
- [ ] 3.4 Implement `src/a2kit/packages/formatter/page.py::encode_page_tsv(page)`. Dump the page envelope via `model_dump(mode="json", exclude={"items"})`, then add `items` as the TSV string and `_items_format = "tsv"`. Serialize the resulting dict with `json.dumps(..., separators=(",",":"), ensure_ascii=False)`.
- [ ] 3.5 Run the suite — encoder tests green.

## 4. format_response accepts new hints

- [ ] 4.1 Extend `FormatHint` literal in `src/a2kit/packages/formatter/__init__.py` to include `"tsv"` and `"page-tsv"`.
- [ ] 4.2 In `format_response`, dispatch `"tsv"` → `encode_tsv` and `"page-tsv"` → `encode_page_tsv`. Set `Response.format` to `"tsv"` for TSV, `"json"` for page-tsv (top-level wire is JSON).
- [ ] 4.3 Add tests covering both new hints from the public API path.
- [ ] 4.4 Mark `toon_or_json` as deprecated in its docstring (export stays).

## 5. ToolDescriptor + App.tool_descriptors() (failing tests first)

- [ ] 5.1 Add `tests/app/test_tool_descriptors.py`: descriptor for typed tool has `return_type` resolved and `format_hint="tsv"` for `-> list[Task]`; descriptor for untyped tool has `return_type=None` and `format_hint="json"`; `app.tools()` still returns callables; `app.tool_descriptors()` returns the typed list; descriptor build is one-shot (instrument `_infer_format_hint` to count calls).
- [ ] 5.2 Add tests for forward-ref resolution: tool with `from __future__ import annotations` and `-> "Task"` resolves correctly; unresolvable forward-ref logs a warning, sets `return_type=None`, `format_hint="json"`, app build succeeds.
- [ ] 5.3 Add `ToolDescriptor` dataclass (in `src/a2kit/tool.py` per design Decision 6). Fields: `name`, `router`, `fn`, `return_type`, `format_hint`, `schema` (schema may be `None` for now if not yet computed elsewhere).
- [ ] 5.4 In `src/a2kit/app.py::add_router`, after registering the router, materialize a `ToolDescriptor` per tool. Call `typing.get_type_hints(fn, include_extras=True)` with the function's `__globals__`. On resolution failure, warn once, fall back to `format_hint="json"`.
- [ ] 5.5 Add `App.tool_descriptors() -> list[ToolDescriptor]` accessor returning a copy of the cached list. Keep `App.tools()` unchanged.
- [ ] 5.6 Run the suite — descriptor tests green.

## 6. CLI runtime reads cached hint

- [ ] 6.1 Add tests in `tests/packages/cli/test_runtime_format.py`: tool `-> list[Task]` (scalar) → CLI auto outputs TSV; tool `-> Page[Task]` (scalar) → CLI auto outputs hybrid JSON-with-embedded-TSV; tool `-> Task` → JSON; untyped tool → JSON; `--format toon` still works (explicit override).
- [ ] 6.2 In `src/a2kit/packages/cli/runtime.py::_invoke_tool_in_process`, look up the descriptor for the dispatched tool and pass its `format_hint` to `format_response` instead of `"auto"`. (Or pass `"auto"` and have `format_response` accept the descriptor — pick the cleaner seam during impl.)
- [ ] 6.3 Confirm `toon_or_json` is no longer called from `_invoke_tool_in_process` or `format_response` (grep step in the test or as an `import-linter` rule if available).
- [ ] 6.4 Run the suite — runtime format tests green.

## 7. CLI builder wires descriptors

- [ ] 7.1 If `_make_tool_command` (in `src/a2kit/packages/cli/builder.py`) needs the descriptor for click-command construction (e.g., to pass `format_hint` into the dispatch closure), thread it through. Otherwise skip — the runtime can look up by `fn.__name__` + router slug.
- [ ] 7.2 Verify `app.cli_extras()` and `build_full_cli` still work end-to-end with at least one typed tool.

## 8. Docs and migration

- [ ] 8.1 Update README's wire-format section: add `tsv` and `page-tsv` to the format-hint table; add a one-paragraph note on the auto-routing change ("type-driven; TOON dropped from auto").
- [ ] 8.2 Add a CHANGELOG entry under v0.23 (or current next-release) covering: auto-menu change, TSV reintroduction, `Page[T]` generic, ~30% token reduction citation (R122).
- [ ] 8.3 Add a short migration note: "Annotate paginated tools as `-> Page[Task]` to opt into hybrid encoding. `Page` (no parameter) and `list[dict]` (untyped) continue to route to JSON."

## 9. Verification

- [ ] 9.1 Run `uv run pytest` — full suite green.
- [ ] 9.2 Run `uv run ruff check` and `uv run mypy` (or whatever the repo uses) — clean.
- [ ] 9.3 `openspec validate type-driven-format-routing` — passes.
- [ ] 9.4 Manual smoke: build a tiny app with one `-> list[Task]` tool and one `-> Page[Task]` tool, run via CLI in `--format auto`, confirm TSV and hybrid output match the spec scenarios byte-for-byte.

## 10. Wrap-up

- [ ] 10.1 Commit on a feature branch and merge to main per project convention (no PR).
- [ ] 10.2 Archive both changes in order with `openspec archive fix-cli-pydantic-render` then `openspec archive type-driven-format-routing`.
- [ ] 10.3 Update `~/Documents/Knowledge/Researches/122-wire-format-token-benchmark/decisions.md` to mark D1, D2, D3 status as `implemented`.
