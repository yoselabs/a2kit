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

