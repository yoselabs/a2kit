## Why

The four `v1-thin-core` commits accumulated abstractions faster than the actual problem warranted. A senior reviewer at DataArt opening `connections/plugin.py`, `signature.py::bind_class_dependencies`, or `app.use()`'s isinstance ladder will read it as **AI slop** — local cleverness, no global restraint. The fat-decorator pitch (`@a2kit.read/write/list_`) is excellent and earns its keep; the framework that grew around it does not.

The gravity well: invent abstraction → notice friction → invent meta-abstraction to manage friction. Six rounds in, we have a Plugin Protocol with six optional methods, four ways to attach an enricher, polymorphic `app.use()` with an ABCMeta gotcha, `Store[ConnT]` Generic introspection, an outer-wrapper-around-Depends to drop class-keys from signatures, and a lint rule whose entire job is defending a boundary we invented in the same commit.

The audience is the whole DataArt practice. The code must read like Python, not framework wizardry. Cut the magic; keep the decorator.

## What Changes

- **BREAKING** Drop `Depends(...)` entirely. Both class-as-key (`Depends(TrackerConn)`) and callable form (`Depends(get_conn)`) are removed. Constructor injection on Routers is the only DI shape. The `uncalled_for` dependency is dropped from `pyproject.toml`.
- **BREAKING** Remove `a2kit.Store[ConnT]` Generic marker. Stores are plain classes; users compose conn → store explicitly in their factory function.
- **BREAKING** Replace polymorphic `app.use(thing)` with three named verbs: `app.add_router(router)`, `app.add_cli(group)`, `app.add_mcp_middleware(middleware)`. No isinstance ladder, no claim/adopt walk.
- **BREAKING** Remove `app.connect(C)` shim entirely. There is no class-claim mechanism to back it.
- **BREAKING** Remove the `Plugin`, `DependsResolver`, `ToolWrapper` Protocols and the `runtime_checkable` machinery. No plugin registry on `App`.
- **BREAKING** Remove the `Connections` plugin class. `ConnectionStore` is a plain class users instantiate directly. The `connections` CLI subcommand is exported as a factory `connections_cli(store)` that users wire via `app.add_cli(...)`.
- **BREAKING** Remove `bind_class_dependencies` and the outer-wrapper that hides class-Depends params from tool input schemas (no class-Depends to hide).
- **BREAKING** Collapse the four enricher attachment forms to one: `@a2kit.read(enricher=fn)` per-tool only. Drop the `Router` class kwarg, drop `self.enricher` instance attr, drop `meta.enricher` plumbing-only paths.
- **BREAKING** Drop the `A2K-CORE-PURITY` lint rule and `src/a2kit/packages/lint/rules/core_purity.py`. There is no architectural boundary worth policing once the plugin Protocol is gone.
- **BREAKING** Remove `a2kit.Plugin`, `a2kit.DependsResolver`, `a2kit.Store`, `a2kit.connect`, `a2kit.use` (replaced by `add_router`/`add_cli`/`add_mcp_middleware`) from public exports.
- **BREAKING** `app.use_factory(...)` is removed. Tests pass factories directly into router constructors.
- Refresh `examples/tracker/` to use constructor injection. Target ≤ 50 LOC for `examples/tracker/server.py + routers.py + store.py` combined.
- Rewrite README "API surface" and "Dependency injection" sections. The DI section becomes one paragraph: "factories are functions; pass them to your router."
- **BREAKING** Delete `make_test_app` entirely. Tests construct an `App` directly: `app = a2kit.App("test"); app.add_router(TasksRouter(fake_get_store))`. Drop `src/a2kit/packages/testing/__init__.py`'s `make_test_app` helper and its `overrides={...}` kwarg.
- CHANGELOG entry documents every removal with a one-line migration recipe.

## Capabilities

### New Capabilities
*(none — this change shrinks rather than adds)*

### Modified Capabilities
*(no `openspec/specs/` baseline exists yet; capabilities are defined inline in this proposal and design.md. The breaking changes touch the de-facto contract from the prior four `v1-thin-core` changes.)*

## Impact

- **Deletes** (in `src/a2kit/`):
  - `plugin.py`, `store.py` (already moved; final delete)
  - `signature.py::bind_class_dependencies` and helpers
  - `app.py::use()` polymorphic dispatch, `_plugins` registry, `connect()`, `use_factory()`, `cli_commands()`, `mcp_middlewares()`, `depends_resolvers()`
  - `routers.py::__init_subclass__(enricher=...)` class kwarg
  - `packages/connections/plugin.py`, `packages/connections/di.py`, `packages/connections/store_marker.py`
  - `packages/lint/rules/core_purity.py`
- **Adds**:
  - `app.add_router(r)`, `app.add_cli(group)`, `app.add_mcp_middleware(m)` — three named verbs on App
  - `packages/connections/cli.py::connections_cli(store)` factory function (replaces the plugin-mediated registration)
- **Refreshes**:
  - `examples/tracker/` — constructor injection throughout
  - README — API surface + DI section rewrites
  - ANTIPATTERNS — drop entries 18, 19 (no plugin boundary to defend); add entry on "factories are functions, not classes"
  - CHANGELOG — migration recipes for every removal
- **Tests**:
  - Delete `tests/test_plugin_protocol.py`, `tests/test_signature_class_depends.py`, `tests/packages/connections/test_plugin.py`, `tests/packages/connections/test_di.py`, `tests/packages/lint/test_rules_core_purity.py`
  - Rewrite `tests/test_app.py` for the three named verbs
  - Adjust `tests/packages/connections/test_factory.py` and `test_cli.py` for the factory-function shape
- **Cold-start invariant unchanged**: `import a2kit < 100ms`. With less code to load, expect a small improvement.
- **Coverage**: target ≥ 92% (current threshold). With ~600 LOC deleted, the existing tests cover a higher fraction.
- **History**: lands as a 5th commit on `v1-thin-core` per user direction. Does not rebase the prior four. The branch's net diff vs `main` will be smaller than after commit 4.
