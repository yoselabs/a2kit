## MODIFIED Requirements

### Requirement: Router slug is an explicit class attribute

A `Router` subclass MUST declare a non-empty `slug: str` class attribute via class-scope assignment (`class WebRouter(Router): slug = "web"`). The framework MUST NOT derive the slug from the class name — there is no verbatim `type(self).__name__` fallback, no trailing-`Router`-suffix strip, and no case conversion. A `Router` subclass that does not declare `slug` MUST raise `TypeError` at subclass-definition time (`Router.__init_subclass__`), naming the subclass and pointing at the `slug: str` requirement with an example assignment. Two routers in the same `App` resolving to the same slug MUST raise `ValueError` at app build time.

The `slug` attribute SHALL be typed as `str` (not `ClassVar[str]`) on the `Router` base class so reads via `self.slug` / `router.slug` type-check uniformly.

This requirement replaces the earlier "derives from class name with explicit override" statement: the code (`src/a2kit/routers.py`) does no derivation at all. It also resolves a three-way contradiction — `core-purity` asserted a verbatim-classname fallback, this spec previously asserted suffix-stripping, and the code requires an explicit attribute. The code is canonical; `core-purity`'s conflicting requirement is removed by the same change.

The `slug` SHALL additionally be the router's **native sub-router namespace** under the homomorphism (ADR 0028 decision 3): each surface SHALL mount the router as a native sub-node keyed by `slug` — `FastMCP.mount(namespace=slug)`, `FastAPI.include_router(prefix, tags=[slug])`, `Typer.add_typer(sub)` — rather than registering its verbs flat on the native root. Consequently a router verb's canonical name SHALL auto-derive as `f"{slug}_{leaf}"` (where `leaf = fn.__name__`) unless the verb pins a `canonical_name_override` (resolved per `tool-descriptors`). The `slug` MUST be a string legal as a native namespace/prefix/command on every surface (`[A-Za-z0-9_]`).

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

#### Scenario: Router mounts as a native sub-router keyed by slug

- **GIVEN** `class Entity(a2kit.Router): slug = "entity"` with a `@a2kit.read def update` verb
- **WHEN** the App is materialized for MCP, HTTP, and CLI
- **THEN** the router mounts as a native sub-node — `FastMCP.mount(namespace="entity")`, `FastAPI.include_router(prefix=…, tags=["entity"])`, `Typer.add_typer(...)`
- **AND** the verb's canonical name auto-derives as `entity_update` on every surface
- **AND** the verb is NOT registered flat as `update` on the native root

#### Scenario: Pinned override under a router stays verbatim

- **GIVEN** `class Jira(a2kit.Router): slug = "jira"` with `@a2kit.read(canonical_name_override="jira_search") def search`
- **WHEN** the router is mounted on any surface
- **THEN** the verb's canonical name is `jira_search` exactly — the slug is NOT re-applied (never `jira_jira_search`)
