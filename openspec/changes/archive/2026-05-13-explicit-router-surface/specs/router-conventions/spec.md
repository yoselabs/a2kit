# router-conventions — explicit-router-surface delta

## MODIFIED Requirements

### Requirement: Router slug is an explicit class attribute

Every `Router` subclass SHALL define `slug: ClassVar[str]` as a
class attribute set to a non-empty string literal. The framework
SHALL NOT derive the slug from `type(self).__name__` or any other
runtime introspection. `Router.__init__` SHALL raise `TypeError`
naming the offending subclass when the attribute is missing,
empty, or not a `str`. The previous suffix-strip derivation
(`TasksRouter` → `tasks`) and the `name=` constructor arg / `name`
class attribute SHALL be removed.

Two routers in the same `App` resolving to the same slug SHALL
raise `ValueError` at `app.add_router` time, as before.

#### Scenario: Explicit slug attribute

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; tools = ()`
- **WHEN** the router is added to an app
- **THEN** its slug is `"tasks"` (verbatim from the class attribute)

#### Scenario: Missing slug raises

- **GIVEN** `class TasksRouter(a2kit.Router): tools = ()` (no `slug`)
- **WHEN** `TasksRouter()` is constructed
- **THEN** `TypeError` is raised naming `TasksRouter` and pointing
  at the missing `slug` class attribute

#### Scenario: Empty slug raises

- **GIVEN** `class TasksRouter(a2kit.Router): slug = ""; tools = ()`
- **WHEN** `TasksRouter()` is constructed
- **THEN** `TypeError` is raised naming `TasksRouter`

#### Scenario: Collision raises (unchanged)

- **GIVEN** two routers with the same `slug` value
- **WHEN** added to the same `App`
- **THEN** the second `app.add_router(...)` raises `ValueError`
  naming the conflicting slug

#### Scenario: Suffix derivation removed

- **WHEN** lint scans the repo
- **THEN** the helper `_derive_slug` and the implicit
  class-name-based fallback are absent; any test that asserted
  derivation behaviour has been rewritten or removed

### Requirement: Router tools are an explicit class attribute

Every `Router` subclass SHALL define `tools: ClassVar[tuple[Callable[..., Any], ...]]`
listing every method decorated with `@a2kit.read`, `@a2kit.write`,
`@a2kit.list_`, or `@a2kit.tool`. The framework SHALL NOT walk
`dir(self)` or otherwise introspect the instance to discover tool
methods. `Router.__init__` SHALL iterate the tuple, resolve each
entry to its bound method via `getattr(self, fn.__name__)`, stamp
the router slug into the method's `_a2kit` meta, and append the
bound method to the internal tool list.

`Router.__init__` SHALL raise `TypeError` naming the offending
subclass when:

- `tools` is missing or not a tuple.
- Any entry in `tools` is not callable.
- Any entry in `tools` carries no `_a2kit` meta (i.e., is not
  decorated with a verb).

A decorated method that is NOT listed in `tools` SHALL NOT
register as a tool. (A linter rule reporting this drift is a
follow-up, not a runtime requirement.)

#### Scenario: Explicit tools tuple

- **GIVEN**
  ```python
  class TasksRouter(a2kit.Router):
      slug = "tasks"

      @a2kit.read()
      async def fetch(self, *, id: str) -> Task: ...

      tools = (fetch,)
  ```
- **WHEN** the router is added to an app
- **THEN** `fetch` is registered as a tool; the bound method's
  `_a2kit` meta carries `router_slug = "tasks"`

#### Scenario: Missing tools attribute raises

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"` (no
  `tools`)
- **WHEN** `TasksRouter()` is constructed
- **THEN** `TypeError` is raised naming `TasksRouter` and pointing
  at the missing `tools` class attribute

#### Scenario: Entry without meta raises

- **GIVEN** a `tools` tuple containing a method that was never
  decorated with a verb
- **WHEN** the router is instantiated
- **THEN** `TypeError` is raised naming the method

#### Scenario: Decorated-but-unlisted method does not register

- **GIVEN** a router defining `tools = (a,)` where `a` is verb-
  decorated, AND another verb-decorated method `b` not present in
  the tuple
- **WHEN** the router is added to an app
- **THEN** only `a` is registered; `b` is silently absent (and a
  follow-up lint rule will flag this drift at static-analysis time)

#### Scenario: `dir()` walk removed

- **WHEN** lint scans the repo
- **THEN** `Router._collect_methods` no longer exists, and no
  `dir(self)` reflection path remains for tool discovery

#### Scenario: `tools` tuple is placed after method definitions

- **GIVEN** a Router class body where `tools = (fetch, update)` is
  written **after** the method definitions for `fetch` and `update`
- **WHEN** Python evaluates the class body
- **THEN** the tuple holds the unbound function references and
  `Router.__init__` resolves each to a bound method at instantiation
  time

#### Scenario: `tools` tuple placed before method definitions is rejected

- **GIVEN** a Router class body where `tools = (fetch,)` is written
  **before** `def fetch(...)` in the same class body
- **WHEN** Python evaluates the class body
- **THEN** a `NameError` is raised (because `fetch` is not yet
  bound in the class namespace at the point `tools` is assigned)
- **AND** the follow-up linter rule (out of scope here, see
  `tasks.md` §5.1) reports any `tools = (...)` placement preceding
  the listed methods so authors get a static-analysis error before
  runtime

## ADDED Requirements

### Requirement: Router lifecycle is a single explicit `lifespan` method

Routers SHALL expose lifecycle work, when needed, via a single
`@contextlib.asynccontextmanager async def lifespan(self):` method
on the subclass; no other lifecycle surface on the Router class
SHALL be auto-discovered by the framework. The pre-`yield` body runs at App startup; the
post-`yield` body runs at App shutdown. `App.add_router(r)` SHALL
read `r.lifespan` (when defined) and compose it into the App's
top-level lifespan using `a2kit.lifespan.compose(...)` (the helper
introduced by the sibling `lifespan-over-lifecycle-hooks`
proposal).

The previous Router auto-bridge — `App.add_router` scanning for
`on_startup` and `on_shutdown` methods on the Router class and
appending them to `App._startup_handlers` / `_shutdown_handlers` —
SHALL be removed. `on_startup` / `on_shutdown` methods on a Router
SHALL NOT be auto-discovered.

The `lifespan` method MAY declare typed kwargs (e.g.
`store: TrackerStore`) which the container resolves before the
context manager is entered, matching the DI behaviour the removed
`on_startup` / `on_shutdown` decorators provided.

#### Scenario: Router lifespan composes into App lifespan

- **GIVEN** a Router subclass with
  ```python
  @asynccontextmanager
  async def lifespan(self):
      await self.store.open()
      try:
          yield
      finally:
          await self.store.close()
  ```
- **WHEN** the router is added to an `App`
- **THEN** `App.add_router(r)` composes `r.lifespan` into the
  App's top-level lifespan via `a2kit.lifespan.compose(...)`
- **AND** at App startup, the pre-`yield` body runs before any
  tool dispatch; at App shutdown, the post-`yield` body runs after
  all tool dispatch has completed

#### Scenario: Legacy `on_startup` / `on_shutdown` methods are not auto-bridged

- **GIVEN** a Router subclass that defines `async def on_startup(self)`
  and/or `async def on_shutdown(self)` methods (the pre-v0.31.0
  shape)
- **WHEN** the router is added to an `App`
- **THEN** those methods SHALL NOT be appended to any App lifecycle
  handler list and SHALL NOT run automatically; the author MUST
  migrate to a `lifespan` method

### Requirement: Router providers are an explicit class-level declaration

Routers SHALL declare DI providers, when needed, via a class
attribute `providers: ClassVar[tuple[ProviderEntry, ...]]` where
each entry is either a type (factory inferred) or a `(type, factory)`
tuple (matching `App.provide(...)`'s signature). `App.add_router(r)`
SHALL read `r.providers` at `add_router` time and install each
entry on the App's container.

This requirement pins existing behaviour as **the canonical
declaration surface** for Router-owned providers, peer to `slug`
and `tools`. The framework SHALL NOT discover providers via
`__init_subclass__`, decorator registries, or any other
side-channel. A reader scanning the Router subclass body sees
every provider it installs.

#### Scenario: Explicit providers install on the App container

- **GIVEN**
  ```python
  class TasksRouter(a2kit.Router):
      slug = "tasks"
      providers = ((TrackerStore, build_store),)
      tools = ()
  ```
- **WHEN** the router is added to an `App`
- **THEN** `App.add_router(r)` calls `self.provide(TrackerStore, build_store)`
  before completing registration

#### Scenario: Discovery surface is exclusively the class declarations

- **WHEN** `App.add_router(r)` runs
- **THEN** the only attributes it reads from `r` to drive
  registration are exactly these four — `slug`, `tools`,
  `providers`, and `lifespan` — and no fifth. No
  `install(self, app)` hook, no `__init_subclass__` registry,
  no `dir()` walk, no marker-attribute side-channel (e.g.
  `_a2kit_attach`) on the Router class or its type.

#### Scenario: Underscored marker attribute is not auto-invoked

- **GIVEN** a Router subclass that defines a class attribute
  `_a2kit_attach = staticmethod(some_callable)` (or any other
  underscore-prefixed marker)
- **WHEN** `App.add_router(r)` is called on this Router
- **THEN** the framework SHALL NOT read or invoke the marker;
  registration completes using only `slug` / `tools` / `providers`
  / `lifespan`. First-party plugins requiring side effects (e.g.
  the connections plugin's dispatch-hook + wire-scope wiring)
  SHALL expose an imperative install function called by the
  consumer (e.g. `install_connections(app, *conn_types)`), not a
  marker on a Router subclass.

## REMOVED Requirements

### Requirement: `Router.install(self, app)` hook

**Reason for removal**: `Router.install` is redundant with the
explicit `providers` tuple and `lifespan` method. Anything the hook
might do (register providers, wire startup work) is now expressed
via the typed class-level declarations `App.add_router` reads. Two
ways to do the same job is exactly the redundancy this proposal
exists to remove. The `getattr(router, "install", None)` call site
in `src/a2kit/app.py` is deleted; the discovery surface is closed
to `slug` / `tools` / `providers` / `lifespan` only.

**Migration**: move provider registrations into the `providers`
tuple and lifecycle work into `lifespan`. No `install` method
remains on Router subclasses.
