## 0. Prerequisites

- [x] 0.1 Confirm `v1-thin-core` branch is at `6f70239` and `make lint` + `make test` are green.
- [x] 0.2 Capture baseline: cold-start ms, test count, coverage %, total core LOC under `src/a2kit/`.

## 1. Phase A — App composition: replace `use()` with three named verbs

- [x] 1.1 In `src/a2kit/app.py`, add `add_router(router)`, `add_cli(group_or_command)`, `add_mcp_middleware(middleware)`. Each appends to a private list (`_routers`, `_cli_extras`, `_mcp_middlewares`).
- [x] 1.2 Remove `App.use()` polymorphic dispatch. Remove `App.connect(C)`. Remove `App.use_factory(...)`. Remove `App._plugins`. Remove plugin-flatten accessors `cli_commands()`, `mcp_middlewares()`, `depends_resolvers()`, `tool_wrappers()`, `plugins()`.
- [x] 1.3 Update `src/a2kit/packages/cli/builder.py::build_full_cli` — read from `app._cli_extras` directly. Drop the `app.cli_commands()` flatten.
- [x] 1.4 Update `src/a2kit/packages/mcp/server.py::build_mcp_server` — read from `app._mcp_middlewares` directly. Drop the `app.mcp_middlewares()` flatten.
- [x] 1.5 Rewrite `tests/test_app.py` for the three named verbs. Delete the polymorphic-use scenarios.
- [x] 1.6 Run `make test` after Phase A. Expect Connections-related tests to fail (Phase B fixes them).

## 2. Phase B — Connections package: collapse to plain classes + factory

- [x] 2.1 Delete `src/a2kit/packages/connections/plugin.py`. Delete `src/a2kit/packages/connections/di.py`.
- [x] 2.2 In `src/a2kit/packages/connections/cli.py`, change `connections_group` from a module-level Click group bound to a registry inside the (deleted) plugin to a factory function `connections_cli(store: ConnectionStore) -> click.Group`. The function builds and returns a fresh group bound to the passed-in store.
- [x] 2.3 Update `src/a2kit/packages/connections/__init__.py` exports: `ConnectionConfig`, `ConnectionStore`, `connections_cli`, plus the existing exception types. Remove `Connections`, `Store`, `find_connections`.
- [x] 2.4 Delete `src/a2kit/packages/connections/store_marker.py`.
- [x] 2.5 Delete `src/a2kit/packages/connections/factory.py::get_conn_factory` if its only callers were the plugin path (verify by grep first; if external callers exist, keep but unbind from plugin).
- [x] 2.6 Rewrite `tests/packages/connections/test_factory.py` to use `ConnectionStore` directly. Rewrite `tests/packages/connections/test_cli.py` to use `connections_cli(store)`.
- [x] 2.7 Delete `tests/packages/connections/test_plugin.py` and `tests/packages/connections/test_di.py`.

## 3. Phase C — DI: drop Depends entirely (class-as-key AND callable form)

- [x] 3.1 In `src/a2kit/signature.py`, delete `bind_class_dependencies` and its outer-wrapper helpers (`_resolve_conn_for`, `_resolve_store_for`, `_drop_class_depends_from_signature`, etc.).
- [x] 3.2 In `src/a2kit/signature.py`, delete every code path that inspects parameter defaults for `uncalled_for` `Depends` sentinels. Keep `find_context_param` (ToolContext detection, unrelated to Depends).
- [x] 3.3 In `src/a2kit/packages/cli/builder.py::_router_group`, drop the `bind_class_dependencies(fn, app)` call site AND any sentinel-stripping logic that hides Depends params from Click options.
- [x] 3.4 In `src/a2kit/packages/mcp/server.py`, drop any `bind_class_dependencies` call site AND any input-schema stripping for Depends sentinels.
- [x] 3.5 In `src/a2kit/__init__.py`, remove any `Depends` re-export (if present).
- [x] 3.6 In `pyproject.toml`, remove `uncalled-for>=0.3,<0.4` from `[project] dependencies`.
- [x] 3.7 Delete `tests/test_signature_class_depends.py` and any other tests whose only purpose is exercising `Depends(...)`.
- [x] 3.8 In `src/a2kit/exceptions.py`, remove `ConnectionKwargMissing` re-exports if any remain.
- [x] 3.9 Update lint rules: remove `A2K-DI-ANNOTATED`, `A2K-DI-IMPORT-LEGACY`, `A2K-DI-IMPORT-SLOW`, `A2K-DI-KWONLY`, `A2K-DI-PYDANTIC-VALIDATE` from `src/a2kit/packages/lint/static.py::ALL_RULES` and delete their rule files. They police a sentinel that no longer exists.
- [x] 3.10 Delete the corresponding lint tests (`tests/packages/lint/test_rules_di*.py`).
- [x] 3.11 Grep `src/` and `tests/` for any remaining `from uncalled_for` or bare `Depends(`. Each result is either a missed callsite or a test to delete.

## 4. Phase D — Plugin Protocol deletion

- [x] 4.1 Delete `src/a2kit/plugin.py`.
- [x] 4.2 Remove `Plugin`, `DependsResolver`, `ToolWrapper` lazy-exports from `src/a2kit/__init__.py`.
- [x] 4.3 Delete `tests/test_plugin_protocol.py`.

## 5. Phase E — Enricher: per-tool only

- [x] 5.1 In `src/a2kit/routers.py`, delete `Router.__init_subclass__(enricher=...)`. Delete the `self.enricher` instance-attr scan in `Router.tools()`. Keep the per-tool `meta.enricher` application path.
- [x] 5.2 Drop the `enricher=staticmethod(...)` setattr workaround comment block.
- [x] 5.3 Verify `tests/test_routers_enricher.py` still passes for the per-tool form. Delete any class-kwarg or instance-attr scenarios.

## 6. Phase F — Lint rule deletion

- [x] 6.1 Delete `src/a2kit/packages/lint/rules/core_purity.py`.
- [x] 6.2 In `src/a2kit/packages/lint/static.py`, remove `A2K_CORE_PURITY` constant. Remove the rule from the `RULES` dispatch tuple. Remove from `ALL_RULES`.
- [x] 6.3 Delete `tests/packages/lint/test_rules_core_purity.py`.
- [x] 6.4 Run `uv run a2kit lint static src/` — confirm no `A2K-CORE-PURITY` strings appear.

## 7. Phase G — Tracker example refresh

- [x] 7.1 Rewrite `examples/tracker/server.py` per design.md sketch. Use `ConnectionStore`, `connections_cli`, `add_router`, `add_cli`. Target single-paragraph composition.
- [x] 7.2 Rewrite `examples/tracker/store.py` — drop `Store[TrackerConn]` base. `class TrackerStore: def __init__(self, conn): ...` with explicit attributes.
- [x] 7.3 Rewrite `examples/tracker/routers.py` — routers take factories via `__init__`, store on `self`, tools use `self.get_store(...)` etc. Per-tool enricher decorator stays where used.
- [x] 7.4 Confirm combined LOC of `server.py + routers.py + store.py` ≤ 50 lines (excl. blanks, imports, comments). If over, simplify until it fits.
- [x] 7.5 Update `tests/examples/tracker/test_server.py` for the new shape.
- [x] 7.6 Smoke test: `uv run python -m examples.tracker.server connections login default ...` → `create_project ...` → `bulk_import_tasks ...`. All four LDD channels still emit; output unchanged.

## 8. Phase H — Delete make_test_app

- [x] 8.1 In `src/a2kit/packages/testing/__init__.py`, delete `make_test_app` entirely. Keep syrupy snapshot extension + any other genuinely-load-bearing helpers; remove only the App-builder.
- [x] 8.2 Grep `tests/` for `make_test_app` callsites. Rewrite each to construct `App` directly: `app = a2kit.App("test"); app.add_router(R(fake_factory))`.
- [x] 8.3 Update README "Testing" section to drop the `make_test_app` snippet; replace with a 3-line direct-construction example.

## 9. Phase I — Docs

- [x] 9.1 README — rewrite "API surface" Core column. Remove `Plugin`, `DependsResolver`, `Store`, `connect`, `use_factory`, `Depends`. Add `add_router`, `add_cli`, `add_mcp_middleware`.
- [x] 9.2 README — rewrite "Dependency injection" section. Single paragraph: "factories are functions; pass them to your router constructor." One short example. Drop the three-shapes table. Drop all `Depends` references.
- [x] 9.3 README — rewrite the tracker quickstart snippet. Match the refreshed example.
- [x] 9.4 README — drop "Authoring a plugin" section if present.
- [x] 9.5 ANTIPATTERNS — remove entries 18 ("don't import packages from core") and 19 ("don't reach into `app._plugins`"). Add new entry: "factories are functions, not classes — don't introduce a Generic-typed marker base."
- [x] 9.6 CHANGELOG — new "de-magic" section under v1.0. Document every removal with a one-line migration recipe per the table in design.md::D9.
- [x] 9.7 `examples/tracker/README.md` — refresh composition section.
- [x] 9.8 Drop the v1.0 lint rules listing of `A2K-CORE-PURITY` from README.

## 10. Phase J — Verification

- [x] 10.1 `uv run pytest -q` — all tests green. Expected delta: ~30-50 fewer tests (deleted scenarios), all remaining green.
- [x] 10.2 `make lint` exits 0. Confirm `A2K-CORE-PURITY` no longer in output.
- [x] 10.3 `uv run ty check src/` — all checks passed.
- [x] 10.4 Cold-start: `python -c 'import time; t=time.time(); import a2kit; print(f"{(time.time()-t)*1000:.1f}ms")'` < 100 ms. Subprocess test confirms `a2kit.packages.connections` not in `sys.modules` after `import a2kit`.
- [x] 10.5 Coverage: ≥ 92% (pyproject `--cov-fail-under` gate). If naturally ≥ 94%, raise gate back to 94 in pyproject.
- [x] 10.6 Tracker E2E smoke: list/create/bulk_import all flow; LDD channels emit with relative timestamps; `<app> --help` shows `connections` subgroup ONLY when the example wires it.
- [x] 10.7 LOC audit: `wc -l src/a2kit/**/*.py` — total core LOC dropped vs baseline by ≥ 400 lines.
- [x] 10.8 Read `src/a2kit/app.py`, `src/a2kit/routers.py`, `src/a2kit/signature.py` end-to-end. Confirm no isinstance ladders, no Generic introspection, no Protocol machinery.

## 11. Phase K — Commit + tag readiness

- [x] 11.1 Single commit on `v1-thin-core`: `de-magic: cut framework, keep the decorator`. Co-authored-by trailer.
- [x] 11.2 Update `CHANGELOG.md` next-version entry with date.
- [x] 11.3 Pause for explicit user authorization before merging `v1-thin-core` → `main` and tagging `v1.0.0`.

## Closeout note (2026-05-09)

The remaining "tag v1.0.0 / merge to main / pause for authorization" tasks are
superseded. The v1.0 ceremony was abandoned in favor of direct-to-main shipping
on the v0.x track; the substantive work landed across v0.20 (de-magic round 1),
v0.21 (de-magic-2), and v0.22 (de-magic-3 / ergonomics). Marking the merge-gate
tasks complete to reflect that the work landed via a different path.
