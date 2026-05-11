# core-composition Specification

## Purpose
TBD - created by archiving change de-magic. Update Purpose after archive.
## Requirements
### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing. The App MUST NOT expose any polymorphic-dispatch verb (no `app.use(thing)`), MUST NOT expose a class-claim shim (no `app.connect(C)`), and MUST NOT expose a factory-registration verb (no `app.use_factory(...)`).

#### Scenario: Adding a Router

- **WHEN** user calls `app.add_router(TasksRouter(get_store))`
- **THEN** the App registers the router for tool collection and CLI subcommand mounting

#### Scenario: Adding a CLI group

- **WHEN** user calls `app.add_cli(connections_cli(store))`
- **THEN** the Click group is mounted as a subcommand on the root CLI built by `a2kit.run(app)`

#### Scenario: Adding MCP middleware

- **WHEN** user calls `app.add_mcp_middleware(my_middleware)`
- **THEN** the middleware is appended after kit-default middleware in `build_mcp_server(app)`

#### Scenario: Polymorphic use is removed

- **WHEN** user code calls `app.use(anything)`
- **THEN** Python raises `AttributeError` because the method does not exist on `App`

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

### Requirement: Enricher attachment is per-tool only

The framework SHALL accept an enricher exclusively through `@a2kit.read(enricher=fn)`, `@a2kit.write(enricher=fn)`, `@a2kit.list_(enricher=fn)`, or `@a2kit.tool(enricher=fn)` decorator parameters. The framework MUST NOT support a `Router` class kwarg form (`class R(a2kit.Router, enricher=fn):`), a `self.enricher` instance attribute, or any other implicit attachment mechanism.

#### Scenario: Per-tool enricher applies on raise

- **WHEN** a tool decorated with `@a2kit.read(enricher=tracker_404)` raises `KeyError`
- **THEN** Router.tools() returns the tool wrapped, and the enricher transforms the exception when invoked

#### Scenario: Class kwarg form is removed

- **WHEN** user writes `class TasksRouter(a2kit.Router, enricher=fn):`
- **THEN** Python raises `TypeError` because `Router.__init_subclass__` no longer accepts the kwarg

### Requirement: A2K-CORE-PURITY lint rule is removed

The `A2K-CORE-PURITY` lint rule SHALL NOT exist. `src/a2kit/packages/lint/rules/core_purity.py` MUST NOT be present. The rule constant MUST NOT appear in `src/a2kit/packages/lint/static.py::ALL_RULES`. Tests for the rule MUST NOT be present in the test tree.

#### Scenario: Lint rule constant is gone

- **WHEN** user runs `uv run a2kit lint static src/`
- **THEN** the output never references `A2K-CORE-PURITY`

#### Scenario: Core may import from packages

- **WHEN** core file imports a package symbol at module level (where doing so is structurally appropriate)
- **THEN** no lint rule fires; the core/packages boundary is no longer policed

### Requirement: Tracker example demonstrates constructor injection

The `examples/tracker/` example SHALL use constructor injection throughout. The combined LOC of `examples/tracker/server.py + examples/tracker/routers.py + examples/tracker/store.py` SHALL be ≤ 50 lines (excluding blank lines, imports, and comments). The example MUST NOT use `Depends(<class>)`, MUST NOT use `Store[ConnT]`, MUST NOT use `app.use(...)`, and MUST NOT reference any `Plugin` class.

#### Scenario: Tracker server composes with three named verbs

- **WHEN** a reader opens `examples/tracker/server.py`
- **THEN** they see `app.add_router(...)` and (optionally) `app.add_cli(connections_cli(...))` and nothing else

#### Scenario: Tracker tools use self-attribute access

- **WHEN** a reader opens any tool method in `examples/tracker/routers.py`
- **THEN** they see `self.get_store(connection)` (or similar) — no `Depends(...)` parameter defaults

### Requirement: Cold-start invariant preserved

`import a2kit` SHALL complete in under 100 milliseconds. Importing `a2kit` MUST NOT pull `a2kit.packages.connections`, `a2kit.packages.enrichers`, `a2kit.packages.mcp`, or any other package into `sys.modules` at import time.

#### Scenario: Cold-start time

- **WHEN** the cold-start subprocess test runs `python -c 'import a2kit'`
- **THEN** wall-clock time is under 100 ms

#### Scenario: Packages not loaded on import

- **WHEN** the cold-start subprocess test inspects `sys.modules` after `import a2kit`
- **THEN** none of `a2kit.packages.connections`, `a2kit.packages.enrichers`, `a2kit.packages.mcp`, `a2kit.packages.cli` appear

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

The `App` class SHALL eager-initialize a `Container` instance during `App.__init__` and SHALL expose `container() -> Container` returning that instance. The return type is non-`Optional`. The `_ensure_container` lazy path is removed.

#### Scenario: Container available immediately after App construction

- **WHEN** `app = App("name")` is constructed and `app.container()` is called
- **THEN** the return value is a `Container` instance
- **AND** the call site is not required to check for `None`

#### Scenario: Single container instance across an App's lifetime

- **WHEN** `app.container()` is called twice on the same `App` instance
- **THEN** both calls return the same object

