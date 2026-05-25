# router-conventions Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: Routers declare enrichers via the `@router.enricher` instance decorator

Routers SHALL declare exception enrichers via the instance-level
`@router.enricher` decorator on a router instance after construction.
The class-level `enrichers: tuple` / `enrich` method shapes are
removed; declaring either at the class body SHALL raise `TypeError`
from `Router.__init_subclass__` (see `a2effect-foundation`).

An enricher SHALL have the signature
`(exc: <BaseException-subclass>) -> AppError | None`. The first
parameter's annotation chooses dispatch shape: a bare `Exception` /
`BaseException` makes it a wide enricher (called on every raise); a
specific exception type makes it narrow (called only on
`isinstance(exc, T)`). The return type SHALL be `AppError | None`
or a subclass union; the runtime validates the returned object at
call time and raises `TypeError` if a non-`AppError` is returned.

Chain order is: per-tool inline (`raises_as` / `translate_to`) →
router enrichers (registration order) → app enrichers (registration
order) → defect quarantine. The first non-None `AppError` wins;
anything escaping all layers is wrapped in `UnexpectedDefect`.

#### Scenario: Narrow enricher fires only on isinstance match

- **GIVEN** `router = TasksRouter()` and a registered enricher
  `def f(exc: LookupError) -> TaskNotFound | None: ...`
- **WHEN** a tool on this router raises a `LookupError`
- **THEN** the framework invokes `f(exc)` and, if non-None, replaces the in-flight exception with the returned `AppError`
- **WHEN** the tool raises a `ValueError` instead
- **THEN** `f` is NOT invoked (no isinstance match)

#### Scenario: Wide enricher catches everything

- **GIVEN** an enricher `def f(exc: Exception) -> AppError | None: ...`
- **WHEN** any non-`AppError` exception escapes the body
- **THEN** `f(exc)` is invoked for every exception; the framework checks the return for None before deciding to translate

#### Scenario: Class-level enrichers/enrich raise at subclass time

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; enrichers = (...)`
- **WHEN** the class statement is evaluated
- **THEN** `TypeError` fires from `Router.__init_subclass__` directing the author to the `@router.enricher` instance decorator

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

The framework SHALL accept per-parameter descriptions sourced from a Google-style `Args:` block in the docstring of any router tool method (any method decorated with `@a2kit.read`, `@a2kit.write`, or `@a2kit.list_`), and SHALL apply them to the MCP input schema and CLI option help per the `tool-description-contract` capability when no explicit pydantic `Field` description is present on the parameter. Router authors MAY therefore omit `Annotated[T, Field(description=...)]` wrappers whose only content is a description that already appears in the docstring.

Router authors SHOULD prefer the docstring when a parameter's only schema metadata is its description, and SHOULD keep an explicit `Field(...)` when the parameter also carries non-description metadata (`examples=`, `ge=`, `le=`, `title=`, etc.) or when the description must differ from the docstring entry.

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

#### Scenario: Router tool mixing docstring and explicit Field

- **GIVEN** a router tool whose `url` parameter uses
  `Annotated[str, Field(examples=["https://x"])]` and whose
  docstring `Args:` has `url: Absolute http(s) URL.`
- **THEN** the resulting MCP schema for `url` carries both the
  description (from the docstring) and the examples (from the `Field`)

#### Scenario: Self and ctx are not described from the docstring

- **GIVEN** a router method whose docstring `Args:` block documents
  `self` or `ctx`
- **THEN** those entries are ignored and do not affect the registered
  tool's MCP input schema

### Requirement: App-time validation rejects decorated-but-unlisted methods

When a Router is added to an App via `App.add_router(router)`, the App SHALL inspect the Router class's own attributes (`type(router).__dict__`) and verify that every method decorated with `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, or `@a2kit.tool` is listed in the router's `tools` tuple. If any decorated method is missing from the tuple, `add_router` SHALL raise `a2kit.exceptions.A2KitDecoratedMethodNotInTools` with the Router class name and the names of the missing methods.

The check applies to the Router class's own attributes only (`cls.__dict__`), not inherited attributes via MRO. A subclass that inherits a decorated method from a base class without re-listing it does NOT fail validation.

#### Scenario: Drift raises with the missing method name

- **GIVEN** a Router subclass with two `@a2kit.read()`-decorated methods, only one of which appears in `tools = (one,)`
- **WHEN** `App("a").add_router(R())` is called
- **THEN** the call raises `A2KitDecoratedMethodNotInTools`
- **AND** the message identifies the Router class name and the unlisted method's name

#### Scenario: All-listed passes through

- **GIVEN** a Router subclass with two decorated methods, both listed in `tools = (one, two)`
- **WHEN** `App("a").add_router(R())` is called
- **THEN** the call succeeds and both tools are registered

#### Scenario: Inherited decorated method does not fail

- **GIVEN** a base Router `B` with a decorated method `b_tool` listed in its own `tools = (b_tool,)`, and a subclass `S(B)` that inherits `b_tool` without overriding it, with `S.tools = (s_only,)` (its own decorated method)
- **WHEN** `App("a").add_router(S())` is called
- **THEN** the call succeeds; `S`'s validation only inspects `S.__dict__`, not the inherited attribute from `B`

#### Scenario: Synthetic `_MetaRouter` passes

- **GIVEN** `App("a", health_tool=True)` which auto-installs the `_MetaRouter` for `_meta.health`
- **WHEN** the App is built
- **THEN** no `A2KitDecoratedMethodNotInTools` is raised — the synthetic router's `tools = (aggregated_health,)` matches its single decorated method

### Requirement: Routers SHALL express lifecycle via `__aenter__` / `__aexit__`

A `Router` subclass MAY opt into lifecycle by implementing the async context manager protocol on the instance: `async def __aenter__(self): ...` and `async def __aexit__(self, exc_type, exc, tb): ...`. The base `a2kit.Router` SHALL NOT declare either method. `App.add_router(instance)` SHALL detect the protocol on the instance via `hasattr(instance, "__aenter__")` and register the instance for lazy entry on first tool dispatch from that router.

#### Scenario: Router with `__aenter__` is detected by `add_router`

- **GIVEN** `class Github(a2kit.Router): slug = "gh"; tools = (...); async def __aenter__(self): ...; async def __aexit__(self, *exc): ...`
- **WHEN** `app.add_router(Github())` is called
- **THEN** the router is registered with lazy-entry tracking
- **AND** neither `__aenter__` nor `__aexit__` has been invoked yet (construction is pure)

#### Scenario: Router without `__aenter__` is dispatched directly

- **GIVEN** a Router subclass that does not implement `__aenter__`
- **WHEN** any of its tools is dispatched
- **THEN** no `__aenter__` is sought; dispatch proceeds against the resolved tool
- **AND** App `__aexit__` does not seek a corresponding `__aexit__` on this router

### Requirement: Router lifecycle SHALL fire lazily on first dispatch

A Router with `__aenter__` SHALL have it invoked exactly once on the first dispatch of any tool belonging to that router. Subsequent dispatches against the same router SHALL NOT re-invoke `__aenter__`. Routers whose tools are never dispatched during the App's lifecycle SHALL NOT have `__aenter__` invoked at all. `__aexit__` SHALL be invoked at App `__aexit__` time only for routers that successfully entered, in LIFO order relative to enter-order.

#### Scenario: First dispatch enters; subsequent dispatches do not re-enter

- **GIVEN** an App with router `Github` (with `__aenter__`) entered (`async with app:`)
- **WHEN** the first `gh.*` tool is dispatched
- **THEN** `Github.__aenter__` ran exactly once
- **WHEN** a second `gh.*` tool is dispatched in the same `async with`
- **THEN** `Github.__aenter__` was NOT invoked again

#### Scenario: Unused router never enters

- **GIVEN** an App with routers `Github` and `Slack` (both with `__aenter__`)
- **WHEN** the App's lifecycle dispatches only `gh.*` tools
- **THEN** `Github.__aenter__` ran; `Slack.__aenter__` did NOT run
- **AND** on App `__aexit__`, `Github.__aexit__` ran; `Slack.__aexit__` did NOT run

### Requirement: Concurrent first-dispatch to a router SHALL coalesce on a single `__aenter__`

Concurrent dispatches to tools of the same router that find the router not-yet-entered SHALL share exactly one `__aenter__` invocation. The framework SHALL guard first-touch with a per-router `asyncio.Lock`. If `__aenter__` raises, the router SHALL NOT be marked as entered; the next dispatch SHALL retry first-touch.

#### Scenario: Two concurrent dispatches share one `__aenter__`

- **GIVEN** a Router with an `__aenter__` that takes a measurable amount of time
- **WHEN** two `asyncio.gather`-dispatched tools target the router simultaneously
- **THEN** `__aenter__` was invoked exactly once
- **AND** both dispatches awaited the same first-touch result

#### Scenario: Failed `__aenter__` does not cache; retry attempts re-enter

- **GIVEN** a Router whose `__aenter__` raises on first attempt
- **WHEN** a tool of that router is dispatched
- **THEN** the dispatch fails with the original exception
- **WHEN** the same tool is dispatched again in the same App lifecycle
- **THEN** `__aenter__` is invoked again (retry); not cached as "already entered"

### Requirement: Router slug is an explicit class attribute

A `Router` subclass MUST declare a non-empty `slug: str` class attribute via class-scope assignment (`class WebRouter(Router): slug = "web"`). The framework MUST NOT derive the slug from the class name — there is no verbatim `type(self).__name__` fallback, no trailing-`Router`-suffix strip, and no case conversion. A `Router` subclass that does not declare `slug` MUST raise `TypeError` at subclass-definition time (`Router.__init_subclass__`), naming the subclass and pointing at the `slug: str` requirement with an example assignment. Two routers in the same `App` resolving to the same slug MUST raise `ValueError` at app build time.

The `slug` attribute SHALL be typed as `str` (not `ClassVar[str]`) on the `Router` base class so reads via `self.slug` / `router.slug` type-check uniformly.

This requirement replaces the earlier "derives from class name with explicit override" statement: the code (`src/a2kit/routers.py`) does no derivation at all. It also resolves a three-way contradiction — `core-purity` asserted a verbatim-classname fallback, this spec previously asserted suffix-stripping, and the code requires an explicit attribute. The code is canonical; `core-purity`'s conflicting requirement is removed by the same change.

#### Scenario: Class-scope slug assignment works

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; tools = ()`
- **WHEN** the app builds and a tool is dispatched on an instance of `TasksRouter`
- **THEN** `instance.slug == "tasks"`

#### Scenario: Missing slug raises at subclass definition

- **GIVEN** `class TasksRouter(a2kit.Router): tools = ()` with no `slug` declaration
- **WHEN** the class statement is evaluated
- **THEN** `TypeError` fires from `Router.__init_subclass__` naming `TasksRouter` and the `slug: str` requirement

#### Scenario: No derivation from class name

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; tools = ()`
- **WHEN** the slug is read
- **THEN** it is the explicit value `"tasks"` — never `"TasksRouter"` (no verbatim fallback) and never `"task"` (no suffix-strip)

#### Scenario: Duplicate slug across routers raises at build

- **GIVEN** two `Router` subclasses in one `App` both declaring `slug = "tasks"`
- **WHEN** the app builds
- **THEN** `ValueError` is raised reporting the slug collision

