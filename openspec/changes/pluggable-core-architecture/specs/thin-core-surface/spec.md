## MODIFIED Requirements

### Requirement: `App` exposes the composition root for routers + plugins

`App(name)` is the composition root. It SHALL provide:

- `use(thing) -> App` — polymorphic dispatch (see `plugin-protocol`).
- `routers() -> list[Router]` — registered routers.
- `tools() -> list[Callable]` — flattened tool callables across
  routers, with all plugin contributions applied (DI resolvers,
  factory rewrites).
- `plugins() -> list[Plugin]` — registered plugins.
- `cli_commands() -> list[click.Command]` — flattened from plugins.
- `mcp_middlewares() -> list[Any]` — flattened from plugins.
- `tool_wrappers() -> list[ToolWrapper]` — flattened from plugins.
- `depends_resolvers() -> list[DependsResolver]` — flattened from
  plugins.
- `set_ldd(*, reports=, events=)` — LDD kill-switch (unchanged).

`App` SHALL NOT have:

- `connect(conn_class)` (sugar for connections plugin only — see
  `connections-plugin`).
- `get_store(conn_class)`.
- `_connection_types`, `_stores`.
- `use_factory(...)` — moves to the connections plugin.
- `factories()`.

#### Scenario: Empty app exposes only routers + plugins
- **WHEN** `app = a2kit.App("x")` is constructed and no `use(...)` calls happen
- **THEN** all accessors return empty lists; no error

#### Scenario: App without connections plugin can't connect
- **WHEN** `App("x").connect(SomeConn)` is called and no `Connections` plugin is registered
- **THEN** `RuntimeError` is raised with a hint to `app.use(Connections())`

### Requirement: Verb decorators stamp `A2KitMeta` (enricher stays in core)

`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, `@a2kit.tool` SHALL
stamp an `A2KitMeta` instance with the existing fields, including
`enricher: EnricherFn | None`. The enricher concept is core (Router
applies it when collecting tools); only specific enricher
implementations live in the `a2kit.packages.enrichers` package.

#### Scenario: enricher kwarg captured on meta
- **WHEN** `@a2kit.read(enricher=fn)` decorates a tool
- **THEN** `meta.enricher is fn`

### Requirement: Router applies enricher when collecting tools

`Router.tools()` SHALL return tool callables wrapped with their
enricher (if any). The wrap is a generic try/except in core
(`src/a2kit/routers.py` or `src/a2kit/_enricher.py`); no import from
any `a2kit.packages.*` module is required. Adapters
(`build_mcp_server`, CLI builder) SHALL NOT call any enricher wrap
themselves — they receive already-wrapped functions.

Per-tool enricher (`@a2kit.read(enricher=fn)`) takes precedence over
router-level enricher (class kwarg or attribute).

#### Scenario: Router wraps tool with enricher
- **WHEN** a tool decorated with `enricher=tracker_404_enricher` is in a router and `router.tools()` is called
- **THEN** the returned callable, when invoked and it raises a `KeyError`, raises the enriched `LookupError` instead

#### Scenario: Adapter does not import enricher wrap
- **WHEN** `src/a2kit/packages/mcp/server.py` is read
- **THEN** it contains no import of `enricher_wrap` (Router applies it)
