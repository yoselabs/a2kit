## Why

Empirical token benchmark (K research R122, 2026-05-09) shows TOON is dominated in the auto-routing menu: ties TSV (~4%) only on pure-scalar rows, and *loses to JSON* by 16-20% on every shape with a list or nested-dict column. Today's `toon_or_json` heuristic actively makes the wrong call for the dominant tracker shape (`list[dict]` with a `labels: list[str]` field). At the same time, the heuristic does an O(rows × columns) walk on every CLI call to pick the format — work that can be done once at app build time from the tool's return-type annotation. And the introspection surface flagged in the original signal (`App.tools()` returns bound methods, no `.return_type` / `.format_hint`) is the missing seam to cache that decision on.

This change replaces runtime heuristic routing with type-driven routing computed at app build, drops TOON from the auto menu, reintroduces TSV for the uniform-tabular case, and upgrades `Page` to a generic envelope so paginated tools (`-> Page[Task]`) get a hybrid wire format: JSON envelope for the cursor/total metadata, TSV string for the rows.

## What Changes

- **BREAKING (auto-format only):** `format_hint="auto"` no longer inspects the payload. It consults the cached `format_hint` on the tool's `ToolDescriptor`, computed at `app.add_router()` time from the function's return-type annotation.
- **BREAKING (auto-format menu):** TOON is removed from the auto menu. It remains available via explicit `format_hint="toon"`. Hand-written callers of `format_response` that relied on auto picking TOON for `list[dict]` see TSV or JSON instead.
- New: `ToolDescriptor` dataclass with `name`, `router`, `fn`, `return_type`, `format_hint`, `schema`, exposed via `App.tool_descriptors()`. `App.tools()` continues to return callables (back-compat).
- New: `_infer_format_hint(return_type)` walks pydantic-aware annotations to compute `"tsv" | "json" | "page-tsv"`. Fallback rule: missing type, `Any`, `Union` of incompatible shapes, unresolved forward ref, or any element type that isn't a scalar-only `BaseModel` → `"json"`.
- New: `Page[T]` is a generic pydantic model. The existing `Page` dataclass at `a2kit/packages/formatter/response.py` is rewritten as `class Page(BaseModel, Generic[T])` with `items: list[T] = []` and `next_cursor: str | None = None`. Construction (`Page(items=[...], next_cursor="x")`) stays compatible. Subclassing to add `total: int | None` / `has_more: bool` becomes natural pydantic field declaration. At inference time, `Page[T]` (or subclass thereof) with scalar-only `T` → `"page-tsv"` hint.
- New: TSV encoder (`encode_tsv`) using stdlib `csv` with `QUOTE_MINIMAL`, tab delimiter, `\n` line terminator. Header from declared field order (not alphabetical). List/dict cells (rare under the type-driven rule) are JSON-blob'd.
- New: hybrid `page-tsv` encoder. Output is JSON: `{"items": "<tsv-string-with-header>", "next_cursor": "...", "_items_format": "tsv"}`. Metadata fields stay structured; `items` becomes a single string the agent parses as a TSV table. Top-level wire format remains `"json"`; `_items_format` discriminator signals embedded TSV.
- `format_response` accepts `format_hint="tsv"` and `"page-tsv"` as first-class options alongside `"auto" | "toon" | "json"`.
- `_invoke_tool_in_process` reads the cached hint from the descriptor instead of running `toon_or_json`.
- `toon_or_json` stays as a public helper for legacy callers but is not used internally; documented as deprecated.

## Capabilities

### New Capabilities
- `tool-descriptors`: typed introspection surface for registered tools — `name`, `router`, `fn`, `return_type`, `format_hint`, `schema`. Computed once at `App.add_router()` time.
- `type-driven-format-routing`: rules for inferring `format_hint` from a tool's return-type annotation, including the dump-scalar definition, the JSON-fallback policy for unanalyzable types, the `Page[T]` generic case, and the TSV / hybrid `page-tsv` encoding contracts.

### Modified Capabilities
- `cli-response-encoding`: the auto-format selection requirement (introduced by `fix-cli-pydantic-render`) is rewritten to consult the cached descriptor hint rather than walking the runtime payload. BaseModel normalization stays unchanged.

## Impact

- **Code:** `src/a2kit/app.py` (descriptor creation in `add_router`, new `tool_descriptors()` accessor); `src/a2kit/routers.py` (descriptor materialization per tool); `src/a2kit/packages/formatter/__init__.py` (encoder dispatch, `format_hint="tsv" | "page-tsv"`); `src/a2kit/packages/formatter/tsv.py` (new — `encode_tsv`); `src/a2kit/packages/formatter/page.py` (new — `encode_page_tsv`); `src/a2kit/packages/formatter/response.py` (`Page` becomes `BaseModel, Generic[T]`); `src/a2kit/packages/formatter/inference.py` (new — `_infer_format_hint`, dump-scalar walker); `src/a2kit/packages/cli/runtime.py` (read cached hint from descriptor); `src/a2kit/packages/cli/builder.py` (build descriptors during command construction).
- **Tests:** new `tests/packages/formatter/test_tsv_encoder.py`; new `tests/packages/formatter/test_page_encoder.py`; new `tests/app/test_tool_descriptors.py`; new `tests/packages/formatter/test_type_inference.py` (table-driven over scalar / list-col / nested-col / deep / Any / Union / forward-ref / pydantic-single / pydantic-list-scalar / pydantic-list-with-list-field / Page[scalar] / Page[non-scalar]).
- **Users:** typed CLI output gets ~30% fewer tokens for the dominant tracker shape (R122 finding). Paginated tools that already return `Page` need to switch from `Page` to `Page[T]` to opt into hybrid encoding (bare `Page` falls back to JSON). Users who relied on TOON in auto mode must opt in explicitly. MCP path unchanged.
- **Docs:** README format-hint table updates (add `tsv`, `page-tsv`); CHANGELOG entry; migration note covering the auto-menu change and `Page` → `Page[T]`.
- **Dependencies:** none added.
- **Prerequisite:** depends on `fix-cli-pydantic-render` landing first (establishes `model_dump(mode="json")` as the canonical normalization step).
- **Out of scope:** envelope variants beyond `Page[T]` (e.g., user-defined custom envelopes with mixed shapes). Hybrid encoding is `Page[T]`-specific in v1; agents can opt into the shape by using `Page[T]` from `a2kit`.
