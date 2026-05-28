## 1. A1 — Formatter `prune_empty` marker

- [x] 1.1 BDD: write failing scenario tests for the 4 spec scenarios in `tests/capabilities/type_driven_format_routing/test_prune_empty.py` (marker prunes None/[]/{}/'', preserves 0/False/Decimal(0), default emits all, schema unchanged)
- [x] 1.2 Add `prune_empty()` helper in `src/a2kit/packages/formatter/` returning a `pydantic.ConfigDict` carrying the marker (e.g. `{"a2kit_prune_empty": True}`) — the simplest API surface
- [x] 1.3 In `format_response` (or the JSON serialization path in `packages/formatter/render.py`): when the model's `model_config.get("a2kit_prune_empty")` is True, post-process the `model_dump(mode="json")` output to drop keys whose value is `None`, `""`, `[]`, or `{}`
- [x] 1.4 Export `prune_empty` at `a2kit.formatter.prune_empty` (or via the package's `__init__`); document via docstring
- [x] 1.5 Make scenario tests pass
- [x] 1.6 Verify schema generation is unchanged — re-run schema-related test suite

## 2. A2 — Runtime tool selection

- [x] 2.1 BDD: write failing scenario tests for the 6 spec scenarios in `tests/capabilities/runtime_tool_selection/` (env restricts MCP, CLI flag restricts CLI, intersection, hidden tool cannot be re-enabled, unknown name fails closed, restart required after env change)
- [x] 2.2 Decide final env-var name (`A2KIT_TOOLS` vs `A2KIT_TOOLS_SELECT`); update tests + spec
- [x] 2.3 Add `resolve_runtime_tool_selection(app, *, env, cli_arg)` in a new module `src/a2kit/packages/serve/runtime_tools.py` (or under `packages/runtime_tools/` if it grows): parses both inputs, validates against `app.tools()` names, computes intersection, raises `ToolSelectionError` on unknown names
- [x] 2.4 Wire selector into `build_mcp_server`: before FastMCP registration, filter the descriptor list through the selector
- [x] 2.5 Wire selector into CLI builder (`packages/cli/builder.py`): before Click subcommand registration, filter through the same selector
- [x] 2.6 Add `--tools` flag to `serve` command (and to the top-level CLI invocation if applicable) via Typer/Click
- [x] 2.7 Make scenario tests pass
- [x] 2.8 Verify hidden-tool case: tools with `visibility="hidden"` are filtered out BEFORE the selector sees them, so the selector cannot re-enable them

## 3. A3 — Top-level Lazy + LddEmission

- [x] 3.1 Add `from a2kit.packages.di import Lazy` to `src/a2kit/__init__.py`
- [x] 3.2 Add `from a2kit.packages.ldd import LddEmission` to `src/a2kit/__init__.py`
- [x] 3.3 Update `__all__` in `src/a2kit/__init__.py` to include `"Lazy"` and `"LddEmission"`
- [x] 3.4 Update `src/a2kit/packages/__init__.py` docstring to declare the namespace as "internal scaffolding" with canonical-import direction to top-level
- [x] 3.5 BDD: write scenario tests for the 3 spec scenarios in `tests/capabilities/thin_core_surface/test_lazy_ldd_emission_top_level.py`
- [x] 3.6 Make scenario tests pass
- [x] 3.7 Search-replace internal a2kit imports (NOT consumer code) where the top-level path is clearly preferred — don't churn unnecessarily

## 4. Docs

- [x] 4.1 Update README: replace any `from a2kit.packages.di import Lazy` references with `from a2kit import Lazy`
- [x] 4.2 Add brief section to README documenting `prune_empty()` formatter marker
- [x] 4.3 Add brief section to README documenting `A2KIT_TOOLS` / `--tools=` selector
- [x] 4.4 Add `Unreleased` entry to `CHANGELOG.md` summarizing A1+A2+A3 + crediting a2web's wish list as the driver
- [x] 4.5 No ADR required (additive features, no architectural decision) — but cite Constitution Article VI (Magic Budget pass) in the commit message

## 5. Cleanup of a2web wishes

- [x] 5.1 Update `~/Workspaces/a2web/docs/history/A2KIT_WISHES_DEFERRED.md`: mark items 1, 3, 4 as RESOLVED (with this a2kit version); update item 5 (`a2kit.desc`) as REFUSED under Article VI
- [x] 5.2 Note: actual a2web cleanup (deleting `_prune_wire`, `ask_only`, etc.) is OUT OF SCOPE for this change — it happens in a separate a2web change after this lands

## 6. Final validation

- [x] 6.1 `make lint` exits 0
- [x] 6.2 `make test` exits 0, no regressions
- [x] 6.3 `make typecheck` clean
- [x] 6.4 `openspec validate a2web-handoff-prep --strict` passes
- [x] 6.5 Verify no breaking changes — existing a2kit consumers (a2web's current shape) build and test successfully
