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

When a `Router` subclass does not define `name`, the framework SHALL
derive the slug by stripping a single trailing `Router` suffix
(case-sensitive) from the class name and lowercasing the remainder.
When `name = "..."` is set on the class, the explicit value SHALL be
used verbatim. Two routers in the same `App` resolving to the same
slug SHALL raise `ValueError` at app build time.

The `slug` attribute SHALL be typed as `str` (not `ClassVar[str]`)
on the `Router` base class. Subclass assignment at class scope
(`class WebRouter(Router): slug = "web"`) continues to be the
documented form and is the conventional pattern. The change in
annotation reflects that `self.slug` is read at instance scope (via
Python's class-attribute resolution path); declaring it as a
`ClassVar` previously fought the type system without affecting
runtime behaviour.

#### Scenario: Class-scope slug assignment continues to work

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; tools = ()`
- **WHEN** the app builds and a tool is dispatched on an instance of `TasksRouter`
- **THEN** `instance.slug == "tasks"` and the slug derivation does not require an instance-scope assignment in `Router.__init__`

#### Scenario: Missing slug still raises a clear error

- **GIVEN** a `Router` subclass with no `slug` declaration and no derivation rule applicable
- **WHEN** the app builds
- **THEN** `TypeError` fires at `Router.__init__` time naming the subclass and pointing at the `slug: str` requirement

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

### Requirement: `Router.lifespan` classmethod surface SHALL be removed

The pre-v0.35 `Router.lifespan` classmethod surface SHALL NOT exist. `App.add_router(instance)` SHALL inspect `type(instance).__dict__` for a `lifespan` attribute and SHALL raise `TypeError` if found, naming the subclass, naming the removed surface (`v0.35`), and pointing at the `__aenter__`/`__aexit__` migration. No alias, no DeprecationWarning, no transitional period.

#### Scenario: Subclass defining `lifespan` raises with migration hint

- **GIVEN** `class Legacy(a2kit.Router): slug = "l"; tools = (); async def lifespan(self): ...`
- **WHEN** `app.add_router(Legacy())` is called
- **THEN** `TypeError` is raised whose message contains both `"Legacy"` and `"__aenter__"`

#### Scenario: Subclass with `__aenter__` is accepted

- **GIVEN** the same `Legacy` rewritten with `__aenter__`/`__aexit__` instead of `lifespan`
- **WHEN** `app.add_router(Legacy())` is called
- **THEN** no `TypeError` is raised and the router is registered

