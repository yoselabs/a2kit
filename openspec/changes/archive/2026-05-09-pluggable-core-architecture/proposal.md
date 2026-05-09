## Why

Core a2kit currently knows about a domain abstraction it shouldn't:

**Connections.** `App.connect(...)`, `App.get_store(...)`,
`App._connection_types`, `signature.bind_class_dependencies` (which
imports `ConnectionConfig`), and connection-specific exceptions
(`ConnectionKwargMissing`, `ConnectionNotRegistered`,
`StoreConnectionTypeUnknown`) all live in `src/a2kit/*.py` (the core
tree). The connections feature is meant to be a plugin package
(`a2kit.packages.connections`), but the core tree imports from it.

The result: a user who doesn't need connections still pays for
connection imports, and the `<app> connections ...` CLI subcommand
appears unconditionally. The "thin core, opt-in packages" promise is
partially broken.

This change formalizes the **plugin contract**: core knows only about
verbs, routers, tool context, enrichers (as a tool-error feature owned
by Router), and a `Plugin` Protocol for everything else. Connections
become a real plugin — registers through the contract, contributes CLI
subcommands and DI resolvers, and doesn't exist when not used. A new
lint rule (`A2K-CORE-PURITY`) makes the boundary unbreakable.

**Note on enrichers.** Enrichers stay a Router feature. The wrap is
just `try: ... except: raise enricher(exc, name)` — protocol-neutral,
no domain knowledge. Router knows how to apply it; the
`a2kit.packages.enrichers` package only ships *specific* enricher
implementations (like `connection_enricher`) that users opt into. The
mechanism is core; the implementations are packages.

## What Changes

### Plugin Protocol (new core abstraction)

- **`a2kit.Plugin` Protocol.** A plugin implements `register(app)` and
  optionally any subset of:
  - `cli_commands() -> list[click.Command]` — append to top-level CLI
    group when present.
  - `mcp_middleware() -> list[Middleware]` — append to FastMCP server.
  - `tool_wrappers() -> list[ToolWrapper]` — wrap each tool fn at
    registration time (used by enrichers).
  - `depends_resolvers() -> list[DependsResolver]` — extend
    `Depends(<class>)` resolution (used by connections).
  - `claim(thing) -> bool` and `adopt(thing, app)` — let
    `app.use(<thing>)` dispatch to a plugin that handles
    foreign-typed registration (e.g. `app.use(TrackerConn)` resolves
    to the `Connections` plugin).
- **`App.use(thing)`** becomes polymorphic:
  1. If `thing` implements `Plugin`, register it.
  2. Else if `thing` is a `Router` instance, add to router registry
     (core-native).
  3. Else: walk registered plugins and find one whose `claim(thing)`
     returns `True`; call its `adopt(thing, app)`.
  4. Else: `TypeError`.
- **`App` exposes `cli_commands()`, `mcp_middlewares()`,
  `tool_wrappers()`, `depends_resolvers()`** — flatten the contributions
  from registered plugins. Builders read these.

### Connections become a plugin

- **`Connections` plugin** at `a2kit.packages.connections.Connections`.
  Responsibilities:
  - `claim(thing) → True` for `type[ConnectionConfig]` subclasses;
    `adopt(...)` records on its own internal registry (not the App).
  - `cli_commands()` returns `[connections_group]`.
  - `depends_resolvers()` returns the `Depends(<conn-class>)` and
    `Depends(<store-class>)` resolvers (currently in
    `a2kit.signature.bind_class_dependencies`).
- **REMOVE from core:**
  - `App.connect(...)`, `App.get_store(...)`, `App._connection_types`,
    `App._stores`.
  - `ConnectionKwargMissing`, `ConnectionNotRegistered`,
    `StoreConnectionTypeUnknown` exceptions move to
    `a2kit.packages.connections.exceptions`.
  - `bind_class_dependencies` and its helpers move to
    `a2kit.packages.connections.di`.
  - `a2kit.Store` marker moves to `a2kit.packages.connections.Store`.
- **Backwards compat:** `App.connect(C)` becomes a thin alias for
  `app.use(Connections())` + `app.use(C)` *only if* the connections
  plugin is loaded; otherwise raises a clear "did you `app.use(Connections())`?"
  error. Document the migration. **BREAKING** for direct use of the
  removed signature.py helpers and removed core exception classes (low
  surface — these are internal to the kit, not user-facing).

### Enrichers stay a Router feature

- **No `Enrichers` plugin.** Enricher is conceptually
  tool-level exception handling; Router is the natural owner.
- **MOVE the generic `wrap_with_enricher(fn, enricher)` helper** from
  `a2kit.packages.enrichers` into core (likely
  `src/a2kit/routers.py` as a private helper, or
  `src/a2kit/_enricher.py`). The wrap is purely
  `try: return fn() / except: raise enricher(exc, tool_name)` — no
  domain knowledge.
- **Router applies enrichers when collecting tools.**
  `router.tools()` returns already-wrapped fns; adapters call them
  without knowing enrichers exist. `build_mcp_server` and CLI runtime
  drop their `enricher_wrap` import.
- **`A2KitMeta.enricher` field stays in core** (it's just a
  `Callable | None`). The class-kwarg form
  (`class TasksRouter(a2kit.Router, enricher=fn):`) stays in core.
  Per-tool decorator form `@a2kit.read(enricher=fn)` stays.
- **`a2kit.packages.enrichers`** keeps only *specific* enricher
  functions (`connection_enricher`, etc.) — user-facing
  implementations they opt into. The mechanism is core; the
  implementations are packages.

### Core-purity lint rule

- **`A2K-CORE-PURITY`.** Static rule. Fires when any file under
  `src/a2kit/*.py` (excluding `src/a2kit/packages/`) imports from
  `a2kit.packages.*`. Files allowed in core:
  `__init__.py`, `__main__.py`, `app.py`, `routers.py`, `runtime.py`,
  `tool.py`, `signature.py`, `metadata.py`, `exceptions.py`,
  `capabilities.py`, `plugin.py` (new). Hard gate at `make lint`.
- The rule enforces the inverse of `A2K-IMPORT-DISCIPLINE` (which
  forbids fastmcp imports outside `packages/mcp`).

### Refreshed tracker example

- `examples/tracker/server.py` becomes:
  ```python
  import a2kit
  from a2kit.packages.connections import Connections, ConnectionConfig
  from a2kit.packages.enrichers import Enrichers

  class TrackerConn(ConnectionConfig): ...

  app = a2kit.App("tracker-mcp")
  app.use(Connections())          # CLI commands + Depends resolvers
  app.use(Enrichers())            # tool-wrapping for enrichers
  app.use(TrackerConn)            # claimed by Connections plugin
  app.use(ProjectsRouter())       # core handles directly
  app.use(TasksRouter())
  ```
- The composition root reads as a manifest of what's active.
  `<app> connections ...` only appears because `Connections()` is
  registered. Drop `Connections()` and the subcommand vanishes.

## Capabilities

### New Capabilities

- `plugin-protocol`: the `a2kit.Plugin` Protocol, `App.use(thing)`
  polymorphic dispatch, and the contribution-flattening accessors
  (`cli_commands()`, `mcp_middlewares()`, `depends_resolvers()`).
- `connections-plugin`: `Connections()` as the canonical plugin for
  connection registration + CLI + DI; encapsulates everything currently
  spread between core and `packages/connections`.
- `core-purity-lint`: `A2K-CORE-PURITY` rule.

### Modified Capabilities

- `thin-core-surface`: removes `App.connect`, `App.get_store`,
  conn-related exceptions, conn-related signature helpers; adds
  `App.use(plugin)` semantics.
- `class-based-dependency-injection`: relocates `Depends(<class>)`
  resolution from core to the `Connections` plugin. Behavior unchanged
  at the call site.

## Impact

- **Code:**
  - `src/a2kit/plugin.py` — new module (Protocol + helpers).
  - `src/a2kit/app.py` — gains `use()` polymorphic dispatch, plugin
    accessors. Loses connect/get_store/store registries.
  - `src/a2kit/signature.py` — loses class-deps resolution code (moves
    to connections package).
  - `src/a2kit/metadata.py` — loses `enricher` field.
  - `src/a2kit/routers.py` — loses enricher kwarg + auto-staticmethod
    logic.
  - `src/a2kit/exceptions.py` — loses connection-specific exceptions.
  - `src/a2kit/packages/connections/{__init__.py, plugin.py, di.py,
    exceptions.py, store.py}` — gains `Connections` plugin, owns the
    DI resolution code, exposes Store marker, exposes conn-specific
    exceptions.
  - `src/a2kit/packages/enrichers/{__init__.py, plugin.py}` — gains
    `Enrichers` plugin, takes over `tool_wrappers()` contribution.
  - `src/a2kit/packages/cli/builder.py` — reads
    `app.cli_commands()` instead of unconditionally adding
    `connections_group`.
  - `src/a2kit/packages/mcp/server.py` — reads `app.mcp_middlewares()`
    + `app.tool_wrappers()` instead of hardcoding enricher_wrap.
  - `src/a2kit/packages/lint/rules/importing.py` (or new
    `core_purity.py`) — implements `A2K-CORE-PURITY`.
- **Tests:**
  - New tests for plugin protocol + dispatch.
  - Connections / enrichers tests move with their packages.
  - Tracker example tests added (the example is the integration
    smoke).
- **Docs:** README "API surface" rewritten — Core column shrinks
  significantly. ANTIPATTERNS gains entry on plugin discipline.
  CHANGELOG documents the breaking moves.
- **Backwards compat:**
  - `App.connect(C)` continues to work *if* `Connections()` is
    registered (sugar; emits no warning). If not, raises a clear
    error. Recommended migration: explicit `app.use(Connections())` +
    `app.use(C)`.
  - `Router(... enricher=fn)` constructor arg continues to work *if*
    `Enrichers()` is registered. If not: silent no-op (per-tool
    decorator still works regardless).
  - Existing tests that don't use connections/enrichers should pass
    unchanged. Existing tests that do will need to register the
    plugins explicitly OR rely on the back-compat sugar.
- **Cold-start:** core gets smaller. `import a2kit` without any
  package imports stays under 100 ms (likely faster). Importing a
  plugin pays only for that plugin.
