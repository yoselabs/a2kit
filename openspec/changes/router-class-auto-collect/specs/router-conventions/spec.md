## ADDED Requirements

### Requirement: Routers auto-collect `@a2kit`-marked tool methods

A `Router` subclass SHALL register its tools by **decorator-marker
collection**: every method carrying an `@a2kit.read`, `@a2kit.write`,
`@a2kit.list_`, or `@a2kit.tool` marker is collected into the router's
tool set by `Router.__init_subclass__` at class-definition time. The
manual `tools: ClassVar[tuple[Callable, ...]]` attribute is **removed**;
authors SHALL NOT declare a `tools=` tuple, and the framework SHALL NOT
require one. A decorated method is a tool by virtue of being decorated.

Collection SHALL be marker-driven, NOT a `dir()` / introspection walk:
the framework reads the verb-decorator metadata stamped on the method
(via the same metadata accessor used elsewhere) and includes a method in
the tool set **only if** it carries that marker. The framework SHALL NOT
collect methods by naming convention, SHALL NOT treat undecorated
methods as tools, and SHALL NOT enumerate `dir(self)` to decide
membership. Iterating the class's own attributes (`cls.__dict__`) to
*locate* markers is permitted; the marker, not the attribute's existence
or name, decides membership.

Inheritance SHALL follow MRO: a subclass that inherits a decorated
method from a base (without re-declaring it) registers that tool; a
subclass that overrides a decorated method registers the override.

#### Scenario: Tuple-free router registers its decorated tools

- **GIVEN** `class Entity(a2kit.Router): slug = "entity"` with two `@a2kit.read`-decorated methods `update` and `search`, and **no** `tools=` tuple
- **WHEN** the router is added to an `App`
- **THEN** both `update` and `search` are registered as tools
- **AND** dispatch resolves each, injecting its typed keyword dependencies

#### Scenario: Undecorated helper is not collected

- **GIVEN** a `Router` subclass with one `@a2kit.read`-decorated tool method and one plain (undecorated) helper method
- **WHEN** the router is added to an `App`
- **THEN** only the decorated method is registered as a tool
- **AND** the undecorated helper is NOT registered (collection is marker-driven, not a `dir()` walk or naming convention)

#### Scenario: Inherited decorated method is collected via MRO

- **GIVEN** a base `Router` `B` with a decorated method `b_tool`, and a subclass `S(B)` that inherits `b_tool` without overriding it and adds its own decorated `s_tool`
- **WHEN** `S` is added to an `App`
- **THEN** both `b_tool` (inherited) and `s_tool` (own) are registered
- **AND** when `S` overrides `b_tool` with its own decorated version, the override is the registered tool

### Requirement: App-time tool registration is collision-free by construction

`App.add_router` SHALL NOT inspect a `tools` tuple, SHALL NOT raise
`A2KitDecoratedMethodNotInTools`, and SHALL rely on the collected tool
set produced at class-definition time by decorator-marker collection
(see "Routers auto-collect `@a2kit`-marked tool methods"). Because there
is no `tools=` tuple for a decorated method to be omitted from, the class
of error formerly guarded by `App.add_router` — a decorated method
missing from the `tools` tuple — is **impossible by construction**.

The synthetic `_MetaRouter` (auto-installed by `App(..., health_tool=True)`
for `_meta.health`) SHALL likewise register its decorated method by
collection, with no `tools=` tuple.

#### Scenario: Adding a decorated method requires no second declaration

- **GIVEN** a `Router` subclass that gains a new `@a2kit.read`-decorated method
- **WHEN** the router is added to an `App`
- **THEN** the new method is registered with no additional bookkeeping — there is no tuple to update and no `A2KitDecoratedMethodNotInTools` to raise

#### Scenario: Drift check is removed

- **GIVEN** any `Router` subclass with one or more `@a2kit`-decorated methods and no `tools=` tuple
- **WHEN** `App("a").add_router(R())` is called
- **THEN** the call succeeds and registers every decorated method
- **AND** `add_router` never raises `A2KitDecoratedMethodNotInTools` (the drift class no longer exists)

#### Scenario: Synthetic `_MetaRouter` passes

- **GIVEN** `App("a", health_tool=True)` which auto-installs the `_MetaRouter` for `_meta.health`
- **WHEN** the App is built
- **THEN** the synthetic router's single `@a2kit`-decorated health method is collected and registered, with no `tools=` tuple involved

## MODIFIED Requirements

### Requirement: Routers declare enrichers via the `@router.enricher` instance decorator

Routers SHALL declare exception enrichers as in-class methods marked
with the `@a2kit.enricher` decorator; the framework SHALL collect every
`@a2kit.enricher`-marked method via `Router.__init_subclass__` at
class-definition time (the same decorator-marker collection used for
tools — see "Routers auto-collect `@a2kit`-marked tool methods"). The
post-construction instance decorator (`router = R(); @router.enricher`)
and the class-level `enrichers: tuple` / `enrich` method shapes are
removed; an enricher is authored exactly once, in the class body, marked
by `@a2kit.enricher`.

An enricher SHALL have the signature
`(self, exc: <BaseException-subclass>) -> AppError | None`. The first
exception parameter's annotation chooses dispatch shape: a bare
`Exception` / `BaseException` makes it a wide enricher (called on every
raise); a specific exception type makes it narrow (called only on
`isinstance(exc, T)`). The return type SHALL be `AppError | None`
or a subclass union; the runtime validates the returned object at
call time and raises `TypeError` if a non-`AppError` is returned.

Chain order is: per-tool inline (`raises_as` / `translate_to`) →
router enrichers (declaration order) → app enrichers (declaration
order) → defect quarantine. The first non-None `AppError` wins;
anything escaping all layers is wrapped in `UnexpectedDefect`.

#### Scenario: Narrow enricher fires only on isinstance match

- **GIVEN** a router with an in-class enricher
  `@a2kit.enricher def f(self, exc: LookupError) -> TaskNotFound | None: ...`
- **WHEN** a tool on this router raises a `LookupError`
- **THEN** the framework invokes the enricher and, if non-None, replaces the in-flight exception with the returned `AppError`
- **WHEN** the tool raises a `ValueError` instead
- **THEN** the enricher is NOT invoked (no isinstance match)

#### Scenario: Wide enricher catches everything

- **GIVEN** an in-class enricher `@a2kit.enricher def f(self, exc: Exception) -> AppError | None: ...`
- **WHEN** any non-`AppError` exception escapes the body
- **THEN** the enricher is invoked for every exception; the framework checks the return for None before deciding to translate

#### Scenario: In-class `@a2kit.enricher` method is auto-collected

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"` with a method `@a2kit.enricher def on_missing(self, exc: LookupError) -> TaskNotFound | None: ...`
- **WHEN** the router is added to an `App` and a tool of that router raises a `LookupError`
- **THEN** the framework had collected `on_missing` at class-definition time and invokes it — no post-construction `@router.enricher` registration was needed

#### Scenario: Post-construction `@router.enricher` instance form is retired

- **GIVEN** author code that constructs a router and applies `@router.enricher` to a free function after construction
- **WHEN** the enricher is authored that way
- **THEN** the sanctioned single channel is the in-class `@a2kit.enricher` marked method; the instance-decorator authoring channel is no longer the supported form

### Requirement: Routers SHALL express lifecycle via `__aenter__` / `__aexit__`

A `Router` subclass MAY opt into lifecycle by implementing the async context manager protocol on the instance: `async def __aenter__(self): ...` and `async def __aexit__(self, exc_type, exc, tb): ...`. The base `a2kit.Router` SHALL NOT declare either method. `App.add_router(instance)` SHALL detect the protocol on the instance via `hasattr(instance, "__aenter__")` and register the instance for lazy entry on first tool dispatch from that router.

#### Scenario: Router with `__aenter__` is detected by `add_router`

- **GIVEN** `class Github(a2kit.Router): slug = "gh"` with one or more `@a2kit`-decorated tool methods and `async def __aenter__(self): ...; async def __aexit__(self, *exc): ...`
- **WHEN** `app.add_router(Github())` is called
- **THEN** the router is registered with lazy-entry tracking
- **AND** neither `__aenter__` nor `__aexit__` has been invoked yet (construction is pure)

#### Scenario: Router without `__aenter__` is dispatched directly

- **GIVEN** a Router subclass that does not implement `__aenter__`
- **WHEN** any of its tools is dispatched
- **THEN** no `__aenter__` is sought; dispatch proceeds against the resolved tool
- **AND** App `__aexit__` does not seek a corresponding `__aexit__` on this router

### Requirement: Router slug is an explicit class attribute

A `Router` subclass MUST declare a non-empty `slug: str` class attribute via class-scope assignment (`class WebRouter(Router): slug = "web"`). The framework MUST NOT derive the slug from the class name — there is no verbatim `type(self).__name__` fallback, no trailing-`Router`-suffix strip, and no case conversion. A `Router` subclass that does not declare `slug` MUST raise `TypeError` at subclass-definition time (`Router.__init_subclass__`), naming the subclass and pointing at the `slug: str` requirement with an example assignment. Two routers in the same `App` resolving to the same slug MUST raise `ValueError` at app build time.

The `slug` attribute SHALL be typed as `str` (not `ClassVar[str]`) on the `Router` base class so reads via `self.slug` / `router.slug` type-check uniformly.

This requirement replaces the earlier "derives from class name with explicit override" statement: the code (`src/a2kit/routers.py`) does no derivation at all. It also resolves a three-way contradiction — `core-purity` asserted a verbatim-classname fallback, this spec previously asserted suffix-stripping, and the code requires an explicit attribute. The code is canonical; `core-purity`'s conflicting requirement is removed by the same change.

#### Scenario: Class-scope slug assignment works

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"` (with zero or more `@a2kit`-decorated tool methods, no `tools=` tuple)
- **WHEN** the app builds and a tool is dispatched on an instance of `TasksRouter`
- **THEN** `instance.slug == "tasks"`

#### Scenario: Missing slug raises at subclass definition

- **GIVEN** `class TasksRouter(a2kit.Router): ...` with one `@a2kit`-decorated method and no `slug` declaration
- **WHEN** the class statement is evaluated
- **THEN** `TypeError` fires from `Router.__init_subclass__` naming `TasksRouter` and the `slug: str` requirement

#### Scenario: No derivation from class name

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"`
- **WHEN** the slug is read
- **THEN** it is the explicit value `"tasks"` — never `"TasksRouter"` (no verbatim fallback) and never `"task"` (no suffix-strip)

#### Scenario: Duplicate slug across routers raises at build

- **GIVEN** two `Router` subclasses in one `App` both declaring `slug = "tasks"`
- **WHEN** the app builds
- **THEN** `ValueError` is raised reporting the slug collision

## REMOVED Requirements

### Requirement: App-time validation rejects decorated-but-unlisted methods

**Reason**: The `tools=` tuple is removed; with decorator-marker
collection there is no tuple for a decorated method to be omitted from,
so the drift class is impossible by construction. The
`A2KitDecoratedMethodNotInTools` check is deleted.

**Migration**: Delete the `tools = (...)` line from each `Router`
subclass; decorated methods are collected automatically. No replacement
declaration is needed. The collision-free guarantee is captured by the
new "App-time tool registration is collision-free by construction"
requirement.
