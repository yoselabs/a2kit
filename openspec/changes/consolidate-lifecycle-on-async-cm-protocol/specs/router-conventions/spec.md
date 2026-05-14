# router-conventions — consolidate-lifecycle-on-async-cm-protocol delta

## ADDED Requirements

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
