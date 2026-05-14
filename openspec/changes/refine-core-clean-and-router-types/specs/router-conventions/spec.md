# router-conventions — refine-core-clean-and-router-types delta

## MODIFIED Requirements

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
