## MODIFIED Requirements

### Requirement: Tool methods declare typed dependencies as kwargs

Tool methods SHALL receive request-scoped dependencies as typed keyword arguments (e.g., `store: TrackerStore`, `connection: ConnectionConfig`). Routers SHALL NOT be required to carry a `get_store: Callable` factory in `__init__` for connection-scoped state.

#### Scenario: Tool with injected store
- **GIVEN** an app with `provide(ConnectionConfig, ...)` and `provide(TrackerStore, ...)` and a router with `async def get_task(self, *, store: TrackerStore, task_id: str) -> Task`
- **WHEN** the tool is dispatched with wire `connection="foo"` and `task_id="x"`
- **THEN** the method receives `store` resolved from `connection="foo"` and `task_id="x"`

#### Scenario: Singleton via __init__ remains supported
- **GIVEN** a router that needs a process-wide logger via `__init__(self, logger)`
- **WHEN** the app is built with `a2kit.testing.app_of("app", TasksRouter(logger=my_logger))`
- **THEN** the router holds the logger as instance state and the framework does not attempt to inject it

### Requirement: Tools are auto-collected from @a2kit-marked methods

A `Router` subclass SHALL NOT declare a `tools` tuple. `Router.__init_subclass__` SHALL auto-collect every method carrying `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, or `@a2kit.tool` metadata (the `_a2kit` marker) by walking the class MRO base-first, deduping by name and preserving definition order. This is marker-collection — methods without the marker (plain helpers) are never collected, and it is NOT a `dir()` / attribute walk. A leftover `tools` tuple is ignored (auto-collect is authoritative) during the migration window.

Auto-collect removes the decorated-but-unlisted drift class by construction: there is no list to keep in sync, so a decorated method can never be silently omitted.

#### Scenario: Decorated methods are collected without a tuple

- **GIVEN** a Router subclass with two `@a2kit.read()`-decorated methods and no `tools` tuple
- **WHEN** `a2kit.testing.app_of("a", R())` is composed
- **THEN** the call succeeds and both methods are registered as tools

#### Scenario: Plain helper methods are not collected

- **GIVEN** a Router subclass with one decorated verb and one undecorated helper method
- **WHEN** the router is constructed
- **THEN** only the decorated verb is collected; the helper is invisible

#### Scenario: Inherited decorated methods are collected

- **GIVEN** a base Router `B` with a decorated method `b_tool` and a subclass `S(B)` adding a decorated method `s_tool`
- **WHEN** `a2kit.testing.app_of("a", S())` is composed
- **THEN** both `b_tool` and `s_tool` are registered (auto-collect walks the MRO)

### Requirement: Routers SHALL express lifecycle via `__aenter__` / `__aexit__`

A `Router` subclass MAY opt into lifecycle by implementing the async context manager protocol on the instance: `async def __aenter__(self): ...` and `async def __aexit__(self, exc_type, exc, tb): ...`. The base `a2kit.Router` SHALL NOT declare either method. When an App composes a router instance, the framework SHALL detect the protocol on the instance via `hasattr(instance, "__aenter__")` and register the instance for lazy entry on first tool dispatch from that router.

#### Scenario: Router with `__aenter__` is detected at composition

- **GIVEN** `class Github(a2kit.Router): slug = "gh"; tools = (...); async def __aenter__(self): ...; async def __aexit__(self, *exc): ...`
- **WHEN** the App composes `Github()` (via the `routers` ClassVar or `a2kit.testing.app_of("app", Github())`)
- **THEN** the router is registered with lazy-entry tracking
- **AND** neither `__aenter__` nor `__aexit__` has been invoked yet (construction is pure)

#### Scenario: Router without `__aenter__` is dispatched directly

- **GIVEN** a Router subclass that does not implement `__aenter__`
- **WHEN** any of its tools is dispatched
- **THEN** no `__aenter__` is sought; dispatch proceeds against the resolved tool
- **AND** App `__aexit__` does not seek a corresponding `__aexit__` on this router
