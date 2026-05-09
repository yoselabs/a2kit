## 0. Prerequisites

- [x] 0.1 Confirm the three prior changes are committed on `v1-thin-core` branch (v1-cleanup-debt, ldd-streaming-reports, dx-polish-tracker-refresh).
- [x] 0.2 Capture baseline: `make lint` exits 0; `make test` → 498 passed; coverage ≥ 94%; cold-start budgets met.

## 1. Core — `Plugin` Protocol

- [x] 1.1 Create `src/a2kit/plugin.py` with the `Plugin` Protocol (`@runtime_checkable`), `ToolWrapper` and `DependsResolver` Protocols. Required: `register(app)`. Optional: `cli_commands`, `mcp_middleware`, `tool_wrappers`, `depends_resolvers`, `claim`, `adopt`. ≤ 80 LOC.
- [x] 1.2 Lazy-export `Plugin`, `ToolWrapper`, `DependsResolver` from `a2kit/__init__.py`.
- [x] 1.3 Mirror tests at `tests/test_plugin_protocol.py`: minimal plugin (only `register`); plugin with all contributions; protocol conformance check.

## 2. App — polymorphic `use()` + plugin accessors

- [x] 2.1 Update `src/a2kit/app.py`. `App._plugins: list[Plugin]`. `App.use(thing)` dispatches: Plugin instance → register; Router instance → router registry; else walk plugins for `claim`/`adopt`; else `TypeError`.
- [x] 2.2 Add accessors: `plugins()`, `cli_commands()`, `mcp_middlewares()`, `tool_wrappers()`, `depends_resolvers()`. Each flattens contributions across `self._plugins`.
- [x] 2.3 REMOVE from core App: `_connection_types`, `_stores`, `_store_classes`, `connect()`, `get_store()`, `store_class_for()`, `_factories`, `use_factory()`, `factories()`. (Some move to Connections plugin; see Phase 3.)
- [x] 2.4 Add backwards-compat sugar: `App.connect(C)` walks plugins, finds one that claims the class, calls `adopt`. Raises with hint if none. NO name-coupling to `Connections` from core.
- [x] 2.5 Update tests: `tests/test_app.py` covers polymorphic `use`, plugin accessors, conn-without-plugin raises.

## 3. Connections plugin migration

- [x] 3.1 Create `src/a2kit/packages/connections/plugin.py` with `Connections` class implementing `Plugin`. Owns `_conn_types: list[type]` registry. `claim(c)` returns `True` for `ConnectionConfig` subclasses. `adopt(c, app)` records on its registry.
- [x] 3.2 Move `ConnectionKwargMissing`, `ConnectionNotRegistered`, `StoreConnectionTypeUnknown` from `src/a2kit/exceptions.py` to `src/a2kit/packages/connections/exceptions.py`.
- [x] 3.3 Move `Store[ConnT]` marker from `src/a2kit/store.py` to `src/a2kit/packages/connections/store_marker.py` (rename to avoid conflict with the existing `store.py` ConnectionStore loader). Drop `src/a2kit/store.py`. Drop core lazy-export of `a2kit.Store`.
- [x] 3.4 Move `bind_class_dependencies`, `_resolve_conn_for`, `_resolve_store_for` from `src/a2kit/signature.py` to `src/a2kit/packages/connections/di.py`. Reshape into the `DependsResolver` Protocol shape: two resolvers (one for conn classes, one for store classes), each with `claim` + `resolve`.
- [x] 3.5 `Connections.depends_resolvers()` returns `[ConnDependsResolver(self), StoreDependsResolver(self)]`. The plugin owns the conn-class registry; resolvers query it.
- [x] 3.6 `Connections.cli_commands()` returns `[connections_group]`. Move `connections_group` import out of `src/a2kit/packages/cli/builder.py`'s default load — the CLI builder reads `app.cli_commands()` instead.
- [x] 3.7 `Connections.tool_wrappers()` returns `[]` for now. (Connection enrichers stay in the Enrichers plugin.)
- [x] 3.8 Move `app.use_factory(factory, *, as_=stub)` semantics to the Connections plugin: `Connections.use_factory(factory, *, as_)` exposed as a plugin method. The legacy `app.use_factory(...)` becomes a deprecated alias that delegates to the Connections plugin (raises if not registered).
- [x] 3.9 Update `src/a2kit/packages/connections/__init__.py` to export `Connections`, `ConnectionConfig`, `ConnectionStore`, `Store`, the moved exceptions. Keep `get_conn_factory` for backwards-compat.
- [x] 3.10 Tests: connections-plugin scenarios (`tests/packages/connections/test_plugin.py`); class-deps via plugin (`tests/packages/connections/test_di.py`); existing connections tests still green.

## 4. Enricher mechanism — move into core, Router applies

- [x] 4.1 Move the generic enricher wrap (`try/except → enricher(exc, tool_name)`) from `src/a2kit/packages/enrichers/__init__.py` into core. Either:
   - Add `_wrap_with_enricher(fn, enricher)` private helper inside `src/a2kit/routers.py`, OR
   - Create `src/a2kit/_enricher.py` with the helper.
   Pick whichever keeps `routers.py` ≤ 80 SLOC. The wrap is purely protocol-neutral; no imports from `a2kit.packages.*`.
- [x] 4.2 Update `Router.tools()` to apply the enricher: for each tool, look up `meta.enricher` (per-tool) or `self.enricher` (router-level), wrap if present. Returns already-wrapped fns.
- [x] 4.3 Update `src/a2kit/packages/mcp/server.py::build_mcp_server` to drop the `from a2kit.packages.enrichers import wrap as enricher_wrap` import and the `enricher_wrap(fn, meta.enricher)` call. Tools come pre-wrapped from the Router.
- [x] 4.4 Update `src/a2kit/packages/cli/runtime.py` similarly — drop `from a2kit.packages.enrichers import wrap` and the call site.
- [x] 4.5 Trim `src/a2kit/packages/enrichers/__init__.py` to only export `connection_enricher` (and any other concrete implementations). The generic `wrap` helper is gone (now in core); the package becomes a small "enricher implementations" library.
- [x] 4.6 Tests: existing enricher tests stay green. Add `tests/test_router_enricher_application.py` to verify Router-applies-enricher behavior end-to-end without going through any package.

## 5. Lint — `A2K-CORE-PURITY`

- [x] 5.1 Create `src/a2kit/packages/lint/rules/core_purity.py` with `rule_a2k_core_purity`. AST walk: for each `Import` / `ImportFrom` node, if the file path is under `src/a2kit/` but NOT under `src/a2kit/packages/`, AND the module starts with `a2kit.packages.`, fire.
- [x] 5.2 Add code constant `A2K_CORE_PURITY = "A2K-CORE-PURITY"` to `src/a2kit/packages/lint/static.py`. Wire into `RULES` dispatch tuple. Add to `ALL_RULES`.
- [x] 5.3 Mirror tests at `tests/packages/lint/test_rules_core_purity.py`. Cover: core file imports package → fires; package file imports another package → silent; package file imports core → silent; tests/ files unaffected; TYPE_CHECKING-block imports silent (rule walks runtime only).
- [x] 5.4 Run `uv run a2kit lint static src/` after the migration — expect zero findings on the refactored core.

## 6. Builder updates

- [x] 6.1 `src/a2kit/packages/cli/builder.py::build_full_cli` — drop hardcoded `connections_group` import + `add_command(connections_group)`. Replace with `for cmd in app.cli_commands(): group.add_command(cmd)`.
- [x] 6.2 Drop `--no-reports` / `--no-events` from the root group? NO — those are LDD core flags, not connections. Keep.
- [x] 6.3 `src/a2kit/packages/mcp/server.py::build_mcp_server` — drop `enricher_wrap` import. Apply tool wrappers via `for w in app.tool_wrappers(): wrapped = w(wrapped, meta)`. Apply `app.mcp_middlewares()` after kit defaults.
- [x] 6.4 Update `_router_group` in CLI builder to apply tool wrappers per-tool same way.

## 7. Tracker example refresh

- [x] 7.1 Update `examples/tracker/server.py` to:
   ```python
   import a2kit
   from a2kit.packages.connections import Connections, ConnectionConfig
   from a2kit.packages.enrichers import Enrichers

   from .connection import TrackerConn
   from .routers import ProjectsRouter, TasksRouter

   app = a2kit.App("tracker-mcp")
   app.use(Connections())
   app.use(Enrichers())
   app.use(TrackerConn)
   app.use(ProjectsRouter())
   app.use(TasksRouter())
   ```
- [x] 7.2 Update `examples/tracker/connection.py` import path: `from a2kit.packages.connections import ConnectionConfig`.
- [x] 7.3 Update `examples/tracker/store.py` import path: `from a2kit.packages.connections import Store` (was `import a2kit; a2kit.Store[...]`).
- [x] 7.4 Update `examples/tracker/routers.py` to use `a2kit.packages.enrichers.RouterMixin` for the class-kwarg enricher form.
- [x] 7.5 Add a smoke test at `tests/examples/tracker/test_server.py` that wires the App and runs a couple of CLI commands end-to-end (verifies the new shape works as documented).

## 8. Docs

- [x] 8.1 README — rewrite "API surface" Core column. Add new "Plugins" subsection. Update tracker snippet.
- [x] 8.2 README — new section "Authoring a plugin" pointing at the Protocol.
- [x] 8.3 ANTIPATTERNS — entry: "Don't import from `a2kit.packages.*` in core. Plugins contribute via the protocol."
- [x] 8.4 ANTIPATTERNS — entry: "Don't reach into `app._plugins` from user code. Use `app.plugins()` and check `isinstance(p, Connections)` if needed."
- [x] 8.5 CHANGELOG — `Next` section: list breaking changes (`A2KitMeta.enricher` removed, `App.connect` requires plugin, `a2kit.Store` moved, etc.) and migration recipes.
- [x] 8.6 Tracker `examples/tracker/README.md` — refresh composition root section.

## 9. Verification

- [x] 9.1 `uv run pytest -q` — all tests pass; existing 498 still green plus new ones.
- [x] 9.2 `make lint` exits 0 (includes `A2K-CORE-PURITY`).
- [x] 9.3 `uv run ty check src/` — All checks passed.
- [x] 9.4 Cold-start: `import a2kit` < 100 ms; `import a2kit` does NOT pull `a2kit.packages.connections` or `a2kit.packages.enrichers` into `sys.modules`. Verified via subprocess test.
- [x] 9.5 Tracker smoke tests:
   - `<app> --help` without `Connections()` plugin: no `connections` subgroup.
   - `<app> --help` with `Connections()` plugin: `connections` subgroup present.
   - `<app> projects create_project --connection=default --name=Demo` works end-to-end.
   - `<app> tasks bulk_import_tasks --connection=default --project-id=... --titles='[...]'` produces interleaved LDD output.
- [x] 9.6 Backwards compat:
   - `app.connect(C)` (legacy call) works when Connections plugin is registered.
   - `app.connect(C)` raises clearly when no plugin is registered.
   - Tests for the v1.0-baseline tracker shape (if any pinned) updated to register the plugins.

## 10. Tag readiness

- [ ] 10.1 Update `CHANGELOG.md` next-version entry with date.
- [ ] 10.2 Pause for explicit user authorization before merging.
