## MODIFIED Requirements

### Requirement: App composition uses three named verbs

Routers SHALL be composed declaratively: an `App` subclass SHALL name its Router classes in a `routers` ClassVar (`class Kay(a2kit.App): name = "kay"; routers = (TasksRouter, ProjectsRouter)`), and tests MAY use `a2kit.testing.app_of(name, *routers)` (which accepts Router classes or instances). The `a2kit.App` class SHALL expose exactly two non-router composition verbs: `add_cli(group_or_command)` and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

`a2kit.App` SHALL be a pure compose-phase builder with no sealed mode. Composition verbs SHALL remain callable at any time, including after the App has been handed to a finisher. A finisher's internal `build(app)` step snapshots the App's current composition into an `AppRuntime`; a composition verb called after `build()` SHALL affect only subsequent builds and SHALL NOT mutate any already-produced `AppRuntime`. There SHALL be no `_sealed` flag and no `TypeError` raised by a composition verb on the basis of App lifecycle state.

A finisher's internal `build(app)` step SHALL invoke `validate_composition(app)` (or its resolved equivalent over the snapshotted descriptors) as part of finalize, so the global canonical-name uniqueness backstop runs on every production build. `build()` SHALL therefore fail loud with the offending verb pair when two verbs resolve to the same canonical name, before any `AppRuntime` is produced. This is the same guarantee `validate_composition(app)` provides standalone; `build()` and the standalone validator share the one `resolve_canonical_name` resolver and so SHALL agree on every resolved name. The standalone validator additionally lets unit tests assert clean composition without paying for a full build.

`App.__init__` SHALL accept the following keyword-only parameters in addition to the positional `name`:
- `config: A2kitConfig | None = None` — optional a2kit-owned configuration instance. When `None`, `App.__init__` SHALL construct a fresh `A2kitConfig()`, which picks up env / `.env` / defaults per the inverted source order. The resolved instance SHALL be exposed as `app.config`.
- `user_config: Any = None` — opaque developer-owned configuration pass-through, exposed as `app.user_config`. a2kit MUST NOT introspect this value.

`App.__init__` SHALL NOT accept a `debug` kwarg. Debug mode is a consumer-owned concern (ADR 0022) and SHALL be set via env `A2KIT_DEBUG=true` or via `A2kitConfig(debug=True)`. An attempt to construct `App("name", debug=True)` SHALL raise the standard unexpected-kwarg `TypeError` (naming the offending kwarg and the CHANGELOG); no bespoke `debug=`-specific migration hint is retained (tombstone sunset, `AGENTS.md` §1).

`App` SHALL NOT expose a `debug` attribute. Consumer-side reads of debug mode SHALL use `app.config.debug`. Subsystem-side reads SHALL resolve `A2kitConfig` via DI (typed dependency). Access to `app.debug` SHALL raise the language-default `AttributeError`; no migration hint is retained.

#### Scenario: Adding a Router

- **WHEN** user authors `class Kay(a2kit.App): name = "kay"; routers = (TasksRouter,)` and constructs `Kay()`
- **THEN** the `App` registers the router for tool collection and CLI
  subcommand mounting

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
- **THEN** routers are composed via the `routers` ClassVar, and exactly `add_cli` and `add_mcp_middleware` are present as verbs, with no polymorphic-dispatch verb alongside them

#### Scenario: Composition after build affects only future builds

- **WHEN** a finisher has built an `AppRuntime` from an `App` and user code then composes another router (a fresh subclass or `app_of` with the added router)
- **THEN** no `TypeError` is raised
- **AND** the already-built `AppRuntime` does not observe `another`
- **AND** a subsequent `build(app)` produces an `AppRuntime` that does include `another`

#### Scenario: build invokes the canonical-name uniqueness backstop

- **WHEN** a finisher calls `build(app)` on an App where two verbs resolve to the same canonical name
- **THEN** `build()` fails loud, naming the colliding canonical name and both offending verbs
- **AND** no `AppRuntime` is produced
- **AND** the same App, validated standalone via `validate_composition(app)`, fails identically (shared resolver)

#### Scenario: App constructed without explicit config gets a fresh A2kitConfig

- **WHEN** user constructs `App("name")` with no `config` kwarg
- **THEN** `app.config` is a fresh `A2kitConfig()` instance reflecting current env / .env / defaults

#### Scenario: App accepts an explicit config instance

- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **AND** no `A2KIT_DEBUG` env var is set
- **THEN** `app.config.debug` is `True`

#### Scenario: App(debug=...) kwarg raises the generic unexpected-kwarg TypeError

- **WHEN** user attempts `App("name", debug=True)`
- **THEN** `TypeError` is raised naming `debug` as an unexpected kwarg and pointing at the CHANGELOG
- **AND** no bespoke `A2KIT_DEBUG` / `A2kitConfig(debug=True)` hint string is required

#### Scenario: env beats config kwarg for debug

- **GIVEN** `A2KIT_DEBUG=false` in process env
- **WHEN** user constructs `App("name", config=A2kitConfig(debug=True))`
- **THEN** `app.config.debug` is `False` (env wins per ADR 0022)

#### Scenario: app.debug attribute access raises a plain AttributeError

- **WHEN** user constructs `App("name")` and reads `app.debug`
- **THEN** the language-default `AttributeError` is raised
- **AND** no migration-hint message content is required

#### Scenario: App.user_config slot accepts arbitrary objects

- **GIVEN** a developer-owned settings instance `my_cfg = MyAppConfig(...)`
- **WHEN** user constructs `App("name", user_config=my_cfg)`
- **THEN** `app.user_config is my_cfg`

#### Scenario: App.user_config defaults to None

- **WHEN** user constructs `App("name")` with no `user_config`
- **THEN** `app.user_config` is `None`

### Requirement: Tracker example demonstrates constructor injection

The `examples/tracker/` example SHALL use constructor injection throughout. The combined LOC of `examples/tracker/server.py + examples/tracker/routers.py + examples/tracker/store.py` SHALL be ≤ 50 lines (excluding blank lines, imports, and comments). The example MUST NOT use `Depends(<class>)`, MUST NOT use `Store[ConnT]`, and MUST NOT reference any `Plugin` class. The example SHALL compose exclusively through the `routers` ClassVar and the named verbs.

#### Scenario: Tracker server composes with the routers ClassVar and named verbs

- **WHEN** a reader opens `examples/tracker/server.py`
- **THEN** they see the routers declared via the `routers` ClassVar and (optionally) `app.add_cli(connections_cli(...))` and nothing else

#### Scenario: Tracker tools use self-attribute access

- **WHEN** a reader opens any tool method in `examples/tracker/routers.py`
- **THEN** they see `self.get_store(connection)` (or similar) — no `Depends(...)` parameter defaults

### Requirement: No test-app helper

The `make_test_app(...)` helper SHALL NOT exist. Tests SHALL construct an `App` using the same composition the production code uses — an `App` subclass with a `routers` ClassVar, or `a2kit.testing.app_of(...)`. The `a2kit.packages.testing` module MUST NOT export `make_test_app`.

#### Scenario: Tests construct App directly

- **WHEN** a test writes `app = a2kit.testing.app_of("test", TasksRouter(fake_get_store))`
- **THEN** the App invokes the router's tools with the fake factory
- **AND** no helper or override map exists in the framework

#### Scenario: make_test_app is not importable

- **WHEN** user writes `from a2kit.packages.testing import make_test_app`
- **THEN** the import raises `ImportError`
