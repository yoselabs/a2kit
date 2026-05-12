# router-conventions Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: Routers declare enrichers via class attribute and/or `enrich` method

Routers SHALL declare exception enrichers using a class attribute `enrichers: list[Callable[[Exception], str | None]] = [...]` and/or an instance method `def enrich(self, exc: Exception) -> str | None`. The stacked `@enriches(...)` decorator and `a2kit.packages.enrichers` module SHALL be removed.

#### Scenario: Class-list enrichers
- **GIVEN** `class TasksRouter(a2kit.Router): enrichers = [generic_404, tracker_404]`
- **WHEN** a tool on this router raises an exception
- **THEN** the framework calls `generic_404(exc)` first; if it returns `None`, calls `tracker_404(exc)`; the first non-None result is used as the user-facing message

#### Scenario: Instance method takes precedence
- **GIVEN** a router defines both `enrichers = [fallback]` and `def enrich(self, exc): ...`
- **WHEN** a tool raises an exception
- **THEN** `self.enrich(exc)` is invoked first; if it returns `None`, the class list is walked

#### Scenario: Old `@enriches` removed
- **WHEN** lint scans the repo
- **THEN** the import `a2kit.packages.enrichers` is reported as removed and any usage triggers an import error

### Requirement: Router slug derives from class name with explicit override

When a `Router` subclass does not define `name`, the framework SHALL derive the slug by stripping a single trailing `Router` suffix (case-sensitive) from the class name and lowercasing the remainder. When `name = "..."` is set on the class, the explicit value SHALL be used verbatim. Two routers in the same `App` resolving to the same slug SHALL raise `ValueError` at app build time.

#### Scenario: Suffix-strip derivation
- **GIVEN** `class TasksRouter(a2kit.Router): pass`
- **WHEN** the router is added to an app
- **THEN** its slug is `"tasks"`

#### Scenario: No suffix to strip
- **GIVEN** `class Tasks(a2kit.Router): pass`
- **WHEN** the router is added to an app
- **THEN** its slug is `"tasks"`

#### Scenario: Explicit override wins
- **GIVEN** `class TasksRouter(a2kit.Router): name = "task-list"`
- **WHEN** the router is added to an app
- **THEN** its slug is `"task-list"` verbatim

#### Scenario: Collision raises
- **GIVEN** two routers both deriving (or set explicitly) to the same slug
- **WHEN** added to the same `App`
- **THEN** `app.add_router(...)` for the second one raises `ValueError` naming the conflicting slug

### Requirement: Tool methods declare typed dependencies as kwargs

Tool methods SHALL receive request-scoped dependencies as typed keyword arguments (e.g., `store: TrackerStore`, `connection: ConnectionConfig`). Routers SHALL NOT be required to carry a `get_store: Callable` factory in `__init__` for connection-scoped state.

#### Scenario: Tool with injected store
- **GIVEN** an app with `provide(ConnectionConfig, ...)` and `provide(TrackerStore, ...)` and a router with `async def get_task(self, *, store: TrackerStore, task_id: str) -> Task`
- **WHEN** the tool is dispatched with wire `connection="foo"` and `task_id="x"`
- **THEN** the method receives `store` resolved from `connection="foo"` and `task_id="x"`

#### Scenario: Singleton via __init__ remains supported
- **GIVEN** a router that needs a process-wide logger via `__init__(self, logger)`
- **WHEN** the app is built with `app.add_router(TasksRouter(logger=my_logger))`
- **THEN** the router holds the logger as instance state and the framework does not attempt to inject it

### Requirement: Router tool methods may rely on the docstring for parameter descriptions

The framework SHALL accept per-parameter descriptions sourced from a
Google-style `Args:` block in the docstring of any router tool
method (any method decorated with `@a2kit.read`, `@a2kit.write`,
`@a2kit.tool`, or `@a2kit.list_`), and SHALL apply them to the MCP
input schema and CLI option help per the `tool-description-contract`
capability when no explicit `Param`/`Field` description is present
on the parameter. Router authors MAY therefore omit
`Annotated[T, a2kit.Param(description=...)]` wrappers whose only
content is a description that already appears in the docstring.

Router authors SHOULD prefer the docstring when a parameter's only
schema metadata is its description, and SHOULD keep
`a2kit.Param(...)` when the parameter also carries non-description
metadata (`examples=`, `ge=`, `le=`, `title=`, etc.) or when the
description must differ from the docstring entry.

#### Scenario: Router tool with docstring-only descriptions

- **GIVEN** a router

  ```python
  class FetchRouter(a2kit.Router):
      @a2kit.read()
      async def fetch(self, *, url: str, timeout: int = 30) -> Result:
          """Fetch a URL.

          Args:
              url: Absolute http(s) URL.
              timeout: Seconds to wait.
          """
  ```

- **WHEN** the router is added to an `App`
- **THEN** the registered tool's MCP input schema has
  `properties.url.description == "Absolute http(s) URL."` and
  `properties.timeout.description == "Seconds to wait."`
- **AND** the corresponding click subcommand's option help shows the
  same strings

#### Scenario: Router tool mixing docstring and explicit Param

- **GIVEN** a router tool whose `url` parameter uses
  `Annotated[str, a2kit.Param(examples=["https://x"])]` and whose
  docstring `Args:` has `url: Absolute http(s) URL.`
- **THEN** the resulting MCP schema for `url` carries both the
  description (from the docstring) and the examples (from `Param`)

#### Scenario: Self and ctx are not described from the docstring

- **GIVEN** a router method whose docstring `Args:` block documents
  `self` or `ctx`
- **THEN** those entries are ignored and do not affect the registered
  tool's MCP input schema

