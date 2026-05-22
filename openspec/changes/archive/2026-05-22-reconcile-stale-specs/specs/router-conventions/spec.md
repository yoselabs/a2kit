## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Routers declare enrichers via class attribute and/or `enrich` method

Routers SHALL declare exception enrichers using a class attribute `enrichers: list[Callable[[Exception], str | None]]` and/or an instance method `def enrich(self, exc: Exception) -> str | None`. There is no stacked `@enriches(...)` decorator and no `a2kit.packages.enrichers` module — neither exists in the source tree.

#### Scenario: Class-list enrichers

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; enrichers = [generic_404, tracker_404]`
- **WHEN** a tool on this router raises an exception
- **THEN** the framework calls `generic_404(exc)` first; if it returns `None`, calls `tracker_404(exc)`; the first non-None result is used as the user-facing message

#### Scenario: Instance method takes precedence

- **GIVEN** a router defines both `enrichers = [fallback]` and `def enrich(self, exc): ...`
- **WHEN** a tool raises an exception
- **THEN** `self.enrich(exc)` is invoked first; if it returns `None`, the class list is walked

#### Scenario: No a2kit.packages.enrichers module

- **WHEN** code runs `import a2kit.packages.enrichers`
- **THEN** the import raises `ModuleNotFoundError` — there is no enrichers package

## REMOVED Requirements

### Requirement: Router slug derives from class name with explicit override

**Reason**: This requirement asserted that an undeclared slug is derived by stripping a trailing `Router` suffix and lowercasing the remainder. The code (`src/a2kit/routers.py`) does no derivation: `slug: str` is a required class attribute and `Router.__init_subclass__` raises `TypeError` if it is absent. The requirement also contradicted `core-purity`, which asserted a different (verbatim class-name) fallback. The contradiction is resolved in favor of the code by the ADDED "Router slug is an explicit class attribute" requirement.

**Migration**: Declare `slug = "..."` explicitly on every `Router` subclass. Do not rely on suffix-strip or any other derivation — a slug-less router raises at subclass definition time.

