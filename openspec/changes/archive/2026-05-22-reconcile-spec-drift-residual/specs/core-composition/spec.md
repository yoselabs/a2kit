## MODIFIED Requirements

### Requirement: App composition uses three named verbs

The `a2kit.App` class SHALL expose exactly three composition verbs: `add_router(router)`, `add_cli(group_or_command)`, and `add_mcp_middleware(middleware)`. Each verb SHALL accept exactly one kind of thing and return the `App` for chaining. The `App` MUST NOT expose any polymorphic-dispatch verb, MUST NOT expose a class-claim shim (no `connect(C)`), and MUST NOT expose a factory-registration verb beyond `provide(...)`.

Once a finisher (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`) has sealed an `App`, calling any of these verbs on it SHALL raise `TypeError`.

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

#### Scenario: Composition after sealing is rejected

- **WHEN** a finisher has sealed an `App` and user code then calls
  `app.add_router(anything)`
- **THEN** it raises `TypeError` explaining the App is sealed

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

## REMOVED Requirements

### Requirement: A2K-CORE-PURITY lint rule is removed

**Reason**: This requirement documented an absent lint rule, citing removed symbols (`A2K-CORE-PURITY`, `A2K-CORE-CLEAN`) — an anti-pattern under ADR 0018, since a living capability spec describes only the current surface.
**Migration**: See CHANGELOG. Core import discipline is policed structurally by `A2K-LAYER` (see `import-acyclicity` and `module-layout-discipline`); core purity is otherwise a design discipline carried by review, with no dedicated lint-rule code.

## ADDED Requirements

### Requirement: Core purity is a review discipline, not a lint rule

Core purity SHALL be maintained as a design discipline enforced through review, with no dedicated lint-rule code in the rule registry. Core import discipline SHALL be policed structurally by the `A2K-LAYER` rule (see `import-acyclicity` and `module-layout-discipline`), which constrains module layering rather than tokens.

#### Scenario: Core may import from packages where layering allows

- **WHEN** a core file imports a package symbol at module level where doing so is structurally appropriate
- **THEN** no token-blocklist lint rule fires; layering is policed by `A2K-LAYER`

#### Scenario: No core-purity rule in the registry

- **WHEN** user runs `uv run a2kit lint static src/` and inspects the rule set
- **THEN** no dedicated core-purity rule code is present; `A2K-LAYER` is the structural enforcement
