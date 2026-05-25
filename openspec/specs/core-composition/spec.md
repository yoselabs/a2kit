# core-composition Specification

## Purpose
TBD - created by archiving change de-magic. Update Purpose after archive.
## Requirements
### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

`a2kit.App` SHALL be a pure compose-phase builder with no sealed mode. Composition verbs SHALL remain callable at any time, including after the App has been handed to a finisher. A finisher's internal `build(app)` step snapshots the App's current composition into an `AppRuntime`; a composition verb called after `build()` SHALL affect only subsequent builds and SHALL NOT mutate any already-produced `AppRuntime`. There SHALL be no `_sealed` flag and no `TypeError` raised by a composition verb on the basis of App lifecycle state.

`App.__init__` SHALL accept the following keyword-only parameters in addition to the positional `name`:
- `config: A2kitConfig | None = None` — optional a2kit-owned configuration instance. When `None`, `App.__init__` SHALL construct a fresh `A2kitConfig()`, which picks up env / `.env` / defaults per the inverted source order. The resolved instance SHALL be exposed as `app.config`.
- `user_config: Any = None` — opaque developer-owned configuration pass-through, exposed as `app.user_config`. a2kit MUST NOT introspect this value.

`App.__init__` SHALL NOT accept a `debug` kwarg. Debug mode is a consumer-owned concern (ADR 0022) and SHALL be set via env `A2KIT_DEBUG=true` or via `A2kitConfig(debug=True)`. An attempt to construct `App("name", debug=True)` SHALL raise `TypeError` carrying a migration hint pointing at the env var and the config kwarg.

`App` SHALL NOT expose a `debug` attribute. Consumer-side reads of debug mode SHALL use `app.config.debug`. Subsystem-side reads SHALL resolve `A2kitConfig` via DI (typed dependency). Access to `app.debug` SHALL raise `AttributeError` with a migration hint naming both replacement paths.

#### Scenario: Adding a Router

- **WHEN** user calls `app.add_router(TasksRouter(get_store))`
- **THEN** the `App` registers the router for tool collection and CLI
  subcommand mounting, and returns the `App`

#### Scenario: Adding a CLI group

- **WHEN** user calls `app.add_cli(connections_cli(store))`
- **THEN** the Click group is mounted as a subcommand on the root CLI
  built by `a2kit.run(app)`

#### Scenario: Adding MCP middleware

- **WHEN** user calls `app.add_mcp_middleware(my_middleware)`
- **THEN** the middleware is appended after kit-default middleware in
  `build_mcp_server(app)`

#### Scenario: Only three named verbs exist

- **WHEN** user inspects the `App` composition surface
- **THEN** exactly `add_router`, `add_cli`, and `add_mcp_middleware` are present, with no polymorphic-dispatch verb alongside them

#### Scenario: Composition after build affects only future builds

- **WHEN** a finisher has built an `AppRuntime` from an `App` and user code then calls `app.add_router(another)`
- **THEN** no `TypeError` is raised
- **AND** the already-built `AppRuntime` does not observe `another`
- **AND** a subsequent `build(app)` produces an `AppRuntime` that does include `another`

#### Scenario: App constructed without explicit config gets a fresh A2kitConfig

- **WHEN** user constructs `App("name")` with no `config` kwarg
- **THEN** `app.config` is a fresh `A2kitConfig()` instance reflecting current env / .env / defaults

#### Scenario: App accepts an explicit config instance

- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **AND** no `A2KIT_DEBUG` env var is set
- **THEN** `app.config.debug` is `True`

#### Scenario: App(debug=...) kwarg raises TypeError with migration hint

- **WHEN** user attempts `App("name", debug=True)`
- **THEN** `TypeError` is raised
- **AND** the error message names `A2KIT_DEBUG` and `A2kitConfig(debug=True)` as the migration targets

#### Scenario: env beats config kwarg for debug

- **GIVEN** `A2KIT_DEBUG=false` in process env
- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **THEN** `app.config.debug` is `False` (env wins per ADR 0022)

#### Scenario: app.debug attribute access raises AttributeError

- **WHEN** user constructs `App("name")` and reads `app.debug`
- **THEN** `AttributeError` is raised
- **AND** the message points at `app.config.debug` (consumer path) and `A2kitConfig` DI (subsystem path)

#### Scenario: App.user_config slot accepts arbitrary objects

- **GIVEN** a developer-owned settings instance `my_cfg = MyAppConfig(...)`
- **WHEN** user constructs `App("name", user_config=my_cfg)`
- **THEN** `app.user_config is my_cfg`

#### Scenario: App.user_config defaults to None

- **WHEN** user constructs `App("name")` with no `user_config`
- **THEN** `app.user_config` is `None`

### Requirement: Dependency injection uses constructor injection only

Routers SHALL receive their dependencies (factories, stores, conn loaders) through `__init__`. Tools defined as methods on the router SHALL access those dependencies via `self`. The framework MUST NOT introspect tool signatures for any DI sentinel. `Depends(...)` MUST NOT exist as a public symbol of `a2kit` in any form. The `uncalled_for` package MUST NOT appear in `pyproject.toml::dependencies`.

#### Scenario: Router accepts factory via constructor

- **WHEN** a router is defined as `class TasksRouter(a2kit.Router): def __init__(self, get_store): self.get_store = get_store`
- **AND** a tool method calls `self.get_store(connection)`
- **THEN** the framework invokes the tool without any signature rewriting

#### Scenario: No Depends symbol exposed

- **WHEN** user writes `from a2kit import Depends`
- **THEN** the import raises `ImportError`

#### Scenario: uncalled_for is not a dependency

- **WHEN** the project is installed in a fresh venv with `uv pip install a2kit`
- **THEN** `uncalled_for` is not present in the installed environment

### Requirement: Stores are plain classes

A "store" SHALL be any plain class. The framework MUST NOT export a `Store[ConnT]` Generic marker. The framework MUST NOT introspect `__orig_bases__` or any other Generic metadata to compose conn → store.

#### Scenario: User defines a store as a plain class

- **WHEN** user writes `class TrackerStore: def __init__(self, conn: TrackerConn): ...`
- **THEN** the framework accepts and uses it without imposing a base class

#### Scenario: Store composition is user code

- **WHEN** user writes `def get_store(connection): return TrackerStore(conn_store.load(connection))`
- **THEN** the framework treats `get_store` as an opaque callable; no introspection occurs

### Requirement: Connections package exposes plain classes and a CLI factory

The `a2kit.packages.connections` package SHALL export `ConnectionConfig` (Pydantic-settings base), `ConnectionStore` (load/save with `${VAR}` and `op://` substitution), and `connections_cli(store)` (a factory returning a Click group with `login`/`logout`/`list`/`show`/`delete` subcommands). The package MUST NOT export a `Connections` plugin class, a `Plugin` Protocol implementation, or any DI resolver classes.

#### Scenario: User wires connection management explicitly

- **WHEN** user writes `app.add_cli(connections_cli(conn_store))`
- **THEN** the `<app> connections {login,logout,list,show,delete}` subcommand is available

#### Scenario: User omits connection wiring

- **WHEN** user constructs an App without calling `app.add_cli(connections_cli(...))`
- **THEN** `<app> --help` shows no `connections` subgroup
- **AND** `import a2kit` does not load the connections package into `sys.modules`

#### Scenario: ConnectionStore loads with substitution

- **WHEN** user calls `conn_store.load("default")` and the saved JSON contains `"token": "${MY_TOKEN}"`
- **THEN** the returned config has `token` resolved from the env at load time
- **AND** subsequent `conn_store.save(cfg)` writes the original `${MY_TOKEN}` placeholder, not the resolved value

### Requirement: No Plugin Protocol or DI resolver Protocol

The framework MUST NOT define a `Plugin` Protocol, a `DependsResolver` Protocol, or a `ToolWrapper` Protocol. The `App` MUST NOT carry a `_plugins` registry, a `cli_commands()` accessor, an `mcp_middlewares()` accessor, a `depends_resolvers()` accessor, or a `tool_wrappers()` accessor. There SHALL be no `claim`/`adopt` walk in App composition.

#### Scenario: Plugin Protocol does not exist

- **WHEN** user writes `from a2kit import Plugin`
- **THEN** the import raises `ImportError` because `Plugin` is not exported

#### Scenario: App has no plugin registry

- **WHEN** user inspects `dir(app)`
- **THEN** there is no `_plugins`, `plugins()`, `cli_commands()`, `mcp_middlewares()`, `depends_resolvers()`, or `tool_wrappers()` attribute

### Requirement: Enricher attachment is via instance decorator only

The framework SHALL accept exception enrichers exclusively via the
instance-level `@router.enricher` / `@app.enricher` decorators on
constructed router / app instances. The framework MUST NOT support:
verb-decorator kwargs (`@a2kit.read(enricher=fn)`), class-level
`enrichers: tuple` attributes, an `enrich(self, exc)` method, or
`Router` subclass kwargs (`class R(a2kit.Router, enricher=fn):`).
See the `router-conventions` requirement on the new instance
decorator and `a2effect-foundation` for the rationale.

#### Scenario: Class-level enrichers attribute raises

- **WHEN** user writes `class TasksRouter(a2kit.Router): enrichers = (...)`
- **THEN** `Router.__init_subclass__` raises `TypeError` directing the
  author to `@router.enricher` after construction

#### Scenario: Verb-decorator enricher kwarg is rejected

- **WHEN** user writes `@a2kit.read(enricher=fn)`
- **THEN** the decorator raises `TypeError` for unknown kwarg `enricher`

### Requirement: Tracker example demonstrates constructor injection

The `examples/tracker/` example SHALL use constructor injection throughout. The combined LOC of `examples/tracker/server.py + examples/tracker/routers.py + examples/tracker/store.py` SHALL be ≤ 50 lines (excluding blank lines, imports, and comments). The example MUST NOT use `Depends(<class>)`, MUST NOT use `Store[ConnT]`, and MUST NOT reference any `Plugin` class. The example SHALL compose exclusively through the three named verbs.

#### Scenario: Tracker server composes with three named verbs

- **WHEN** a reader opens `examples/tracker/server.py`
- **THEN** they see `app.add_router(...)` and (optionally) `app.add_cli(connections_cli(...))` and nothing else

#### Scenario: Tracker tools use self-attribute access

- **WHEN** a reader opens any tool method in `examples/tracker/routers.py`
- **THEN** they see `self.get_store(connection)` (or similar) — no `Depends(...)` parameter defaults

### Requirement: Cold-start invariant preserved

`import a2kit` SHALL complete in under 100 milliseconds. Importing `a2kit` MUST NOT pull `a2kit.packages.connections`, `a2kit.packages.mcp`, or any other package into `sys.modules` at import time.

#### Scenario: Cold-start time

- **WHEN** the cold-start subprocess test runs `python -c 'import a2kit'`
- **THEN** wall-clock time is under 100 ms

#### Scenario: Packages not loaded on import

- **WHEN** the cold-start subprocess test inspects `sys.modules` after `import a2kit`
- **THEN** none of `a2kit.packages.connections`, `a2kit.packages.mcp`, `a2kit.packages.cli` appear

### Requirement: No test-app helper

The `make_test_app(...)` helper SHALL NOT exist. Tests SHALL construct an `App` directly using the same composition verbs as production code. The `a2kit.packages.testing` module MUST NOT export `make_test_app`.

#### Scenario: Tests construct App directly

- **WHEN** a test writes `app = a2kit.App("test"); app.add_router(TasksRouter(fake_get_store))`
- **THEN** the App invokes the router's tools with the fake factory
- **AND** no helper or override map exists in the framework

#### Scenario: make_test_app is not importable

- **WHEN** user writes `from a2kit.packages.testing import make_test_app`
- **THEN** the import raises `ImportError`

### Requirement: `App.container()` returns the active container

The compose-phase `App` class SHALL eager-initialize a `Container` instance during `App.__init__` and SHALL expose `container() -> Container` returning that instance. The return type is non-`Optional`. This compose-phase container accumulates `provide(...)` registrations and remains mutable for the App's whole lifetime — it is never sealed.

A finisher's internal `build(app)` step SHALL NOT seal or mutate the compose-phase container. It SHALL snapshot the App's provider registrations and wire-scopes into a separate, freshly constructed `Container` owned by the resulting `AppRuntime`. Each `build()` call SHALL produce an independent runtime container, so one `App` MAY be handed to more than one finisher.

#### Scenario: Container available immediately after App construction

- **WHEN** `app = App("name")` is constructed and `app.container()` is called
- **THEN** the return value is a `Container` instance
- **AND** the call site is not required to check for `None`

#### Scenario: Single compose-phase container across an App's lifetime

- **WHEN** `app.container()` is called twice on the same `App` instance
- **THEN** both calls return the same object

#### Scenario: Each build produces an independent runtime container

- **WHEN** the same `App` is handed to two finishers in turn
- **THEN** each `build()` constructs a fresh runtime `Container` from the App's registrations
- **AND** neither runtime container is the App's compose-phase container

### Requirement: Core purity is a review discipline, not a lint rule

Core purity SHALL be maintained as a design discipline enforced through review, with no dedicated lint-rule code in the rule registry. Core import discipline SHALL be policed structurally by the `A2K-LAYER` rule (see `import-acyclicity` and `module-layout-discipline`), which constrains module layering rather than tokens.

#### Scenario: Core may import from packages where layering allows

- **WHEN** a core file imports a package symbol at module level where doing so is structurally appropriate
- **THEN** no token-blocklist lint rule fires; layering is policed by `A2K-LAYER`

#### Scenario: No core-purity rule in the registry

- **WHEN** user runs `uv run a2kit lint static src/` and inspects the rule set
- **THEN** no dedicated core-purity rule code is present; `A2K-LAYER` is the structural enforcement

