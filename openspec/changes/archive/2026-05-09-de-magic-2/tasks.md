## 1. Additive groundwork (non-breaking)

- [x] 1.1 Add `A2K-EXTRA-NAMESPACE` lint rule (AST visitor for `extra[<str>] = ...` writes); register in `static.py::ALL_RULES`
- [x] 1.2 Add `A2K-CORE-CLEAN` lint rule (AST visitor scoped to `src/a2kit/*.py` excluding `packages/`); register in `static.py::ALL_RULES`; ship as warn-only initially
- [x] 1.3 Tests for both rules: `tests/packages/lint/test_core_purity.py` and `tests/packages/lint/test_extra_namespace.py`
- [x] 1.4 Run `a2kit lint static` against current source — expect both rules to fire (proves they work; baseline for cleanup)

## 2. Feature-decorator stacking

- [x] 2.1 Define `enriches(fn)` decorator in `a2kit.packages.enrichers` — sets `_a2kit_pending_extra["a2kit.enricher"]` on the wrapped fn (transient attr consumed by verb decorator)
- [x] 2.2 Define `lists(...)` decorator in `a2kit.packages.mcp.listview` (or new `a2kit.packages.mcp.lists`) — sets `_a2kit_pending_extra["a2kit.list_view"]`
- [x] 2.3 Define `reports(ReportT)` decorator in new `a2kit.packages.mcp.reports` — computes pydantic schema there, sets both `extra["a2kit.report_type"]` and `extra["a2kit.report_schema"]`
- [x] 2.4 Update `tool.py::_stamp` to consume `_a2kit_pending_extra` from `fn` and merge into `meta.extra`; clean up the transient attr
- [x] 2.5 Tests: `tests/test_decorator_stacking.py` covering verb-only, verb+enricher, verb+lists, verb+reports, all-three
- [x] 2.6 Migrate tracker example: `examples/tracker/routers.py` — switch from `enricher=` kwarg to `@enriches(...)` stacked decorator
- [x] 2.7 Migrate any test that uses `enricher=`/`list_view=`/`report=` kwargs (grep shows ~8 sites)

## 3. Drop feature kwargs from core decorators

- [x] 3.1 Remove `enricher`, `list_view`, `router_slug`, `report` kwargs from `a2kit.tool.read/write/list_/tool` and `_stamp`
- [x] 3.2 Remove `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug` fields from `A2KitMeta` (in `metadata.py`)
- [x] 3.3 Remove `EnricherFn` type alias from `metadata.py`; export it from `a2kit.packages.enrichers` only
- [x] 3.4 Remove `_report_schema` helper + pydantic import from `tool.py`
- [x] 3.5 Update `routers.py::Router.tools()`: drop the `_wrap_with_enricher` loop. Adapters now read `meta.extra.get("a2kit.enricher")` themselves
- [x] 3.6 Delete `_wrap_with_enricher` from `routers.py`; expose `wrap_with_enricher` from `a2kit.packages.enrichers` (already exists as `wrap`)
- [x] 3.7 Update CLI builder: at the point where it iterates router tools, wrap with enricher from `extra` if present
- [x] 3.8 Update MCP server: same pattern — wrap with enricher from `extra` before registering
- [x] 3.9 Run full test suite — fix any callsite still using old kwargs

## 4. Bound-method router collection

- [x] 4.1 Rewrite `Router._collect_methods` to use `inspect.getmembers(self, predicate=...)` returning bound methods filtered by `getattr(m, '_a2kit', None) is not None`
- [x] 4.2 Verify `get_meta(bound_method)` still returns the meta (attribute fall-through via `MethodType`)
- [x] 4.3 Delete `_bind_if_method` from `a2kit/packages/cli/builder.py`
- [x] 4.4 Update `_router_group(router)` to call `_make_tool_command(fn)` directly with the bound method (no rebind)
- [x] 4.5 Run full test suite — fix any signature-introspection callsite that depended on raw class-dict functions

## 5. Closure-based CLI builder (no monkey-patch, no ContextVar)

- [x] 5.1 Change `LazyGroup._lazy` value type from `str` (import path) to `Callable[[], click.Command]` (factory). Backwards-compatible parsing for the string form can be dropped since only `serve` uses it.
- [x] 5.2 Update `build_full_cli(app)` to register `serve` via `lazy_subcommands={"serve": lambda: _build_serve_command(app)}` where `_build_serve_command` imports fastmcp lazily inside its callback
- [x] 5.3 Move `--no-reports/--no-events` flag handling out of the per-tool callback's `_APP_CTX.get()` lookup; instead, make those flags' callbacks set values on a closure-captured `dict` or pass via `click.Context.obj`
- [x] 5.4 Delete `_wrap_main_with_app_ctx` from `builder.py`
- [x] 5.5 Delete `a2kit/packages/cli/app_ctx.py` (the `_APP_CTX` ContextVar module)
- [x] 5.6 Update tracker E2E smoke to confirm `--no-reports` still works without ContextVar
- [x] 5.7 Cold-start benchmark: verify `import a2kit; a2kit.run` path still doesn't import fastmcp until `serve` is invoked

## 6. WriteNotAllowed migration

- [x] 6.1 Define `WriteNotAllowed` in `a2kit.packages.connections.exceptions` (copy current shape, drop `tool_name` if unused)
- [x] 6.2 Delete `WriteNotAllowed` from `a2kit.exceptions`
- [x] 6.3 Remove `WriteNotAllowed` entry from `a2kit/__init__.py` `_LAZY_ATTRS` and `__all__`
- [x] 6.4 Update any importer (grep `from a2kit.exceptions import WriteNotAllowed` and `import a2kit; ... a2kit.WriteNotAllowed`)

## 7. Drop slug derivation

- [x] 7.1 Replace `_slugify` + the `__init__` body in `routers.py` with the 3-line lookup: `name=` → `cls.name` → `type(self).__name__`
- [x] 7.2 Delete `_slugify` (and its import of `re`)
- [x] 7.3 Update tracker routers (`examples/tracker/routers.py`) to set `name = "projects"` and `name = "tasks"` class attrs
- [x] 7.4 Update any test that asserts on auto-derived slugs (grep `assert.*slug`)
- [x] 7.5 Add ANTIPATTERNS.md entry: "Don't rely on slug derivation; set `name` explicitly"

## 8. Lint flip + final sweep

- [x] 8.1 Run `a2kit lint static` — `A2K-CORE-CLEAN` should now report zero hits in `src/a2kit/*.py` (excluding packages)
- [x] 8.2 Flip `A2K-CORE-CLEAN` from warn to hard error in CI config / `make lint`
- [x] 8.3 Same for `A2K-EXTRA-NAMESPACE`
- [x] 8.4 Update `README.md` API surface table: drop the four feature kwargs from verb decorators
- [x] 8.5 Update `ANTIPATTERNS.md`: new entry covering decorator-kwarg accumulation; cross-reference D1 of design.md
- [x] 8.6 Update `CHANGELOG.md`: single 0.21.0 entry describing final shape (per the v0.20 single-entry convention)

## 9. Release

- [x] 9.1 Bump version 0.20.0 → 0.21.0 in `pyproject.toml`
- [x] 9.2 Run full gate: `make lint`, `make test`, `make e2e` (tracker smoke); coverage stays ≥92
- [x] 9.3 Cold-start benchmark snapshot — record in CHANGELOG
- [x] 9.4 Merge to main; tag `v0.21.0`; push tag and main
