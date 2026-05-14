# core-purity Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: Core exposes only a typed dispatch hook protocol

`src/a2kit/*.py` (excluding `packages/`) SHALL define a single dispatch hook protocol consumed by tool dispatch, taking a tool function and a dict of wire kwargs and returning a dict of resolved kwargs. Core SHALL NOT import or reference `Container`, `ConnectionConfig`, `TrackerStore`, or any other concrete domain or DI type.

#### Scenario: Lint forbids container imports in core
- **WHEN** `A2K-CORE-CLEAN` scans `src/a2kit/routers.py`, `src/a2kit/tool.py`, `src/a2kit/__init__.py`, etc.
- **THEN** it reports any import of `a2kit.packages.connections.container.Container` or any reference to `ConnectionConfig` as a violation

#### Scenario: Hook protocol is the only DI surface in core
- **WHEN** the dispatch hook is defined
- **THEN** it appears as a `Protocol` with a single `__call__(fn, wire_kwargs) -> resolved_kwargs` shape and no other DI-related symbol exists in core

### Requirement: Apps without a Connections plugin get an identity hook

When an `App` has no provider registry (no `App.provide(...)` calls and no Connections plugin attached), the framework SHALL use an identity dispatch hook that returns `wire_kwargs` unchanged.

#### Scenario: Empty app builds and dispatches
- **GIVEN** an `App("demo")` with one router and zero `provide()` calls
- **WHEN** a tool is dispatched
- **THEN** the dispatch hook returns the wire kwargs unchanged
- **AND** no Container instance is constructed

### Requirement: A2KitMeta.extra remains the only extension point

Core's `A2KitMeta` dataclass SHALL retain `extra: dict[str, Any]` as the only namespaced extension carrier. The DI feature SHALL NOT add new fields to `A2KitMeta`. Any container-related per-tool data SHALL live in `meta.extra` under an `a2kit.di.*` key prefix.

#### Scenario: meta.extra carries injection-related metadata
- **GIVEN** the framework partitions a tool's kwargs at collect time
- **WHEN** the partition result is stored
- **THEN** it is written to `meta.extra["a2kit.di.partition"]` and not to a new field on `A2KitMeta`

### Requirement: Verb decorators carry no feature kwargs

`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, `@a2kit.tool` MUST accept only `name`, `tags`, and `annotations` keyword arguments. Other behavior is attached via stacked feature decorators.

#### Scenario: Reject enricher kwarg
- **WHEN** code calls `@a2kit.read(enricher=fn)`
- **THEN** Python raises `TypeError: read() got an unexpected keyword argument 'enricher'`

#### Scenario: Reject report kwarg
- **WHEN** code calls `@a2kit.read(report=MyReport)`
- **THEN** Python raises `TypeError`

#### Scenario: Stacked feature decorators compose
- **WHEN** a function is decorated with `@a2kit.read()` outside `@enriches(fn)` outside `@reports(MyReport)`
- **THEN** the resulting `A2KitMeta.extra` contains both `a2kit.enricher` and `a2kit.report_type` keys

### Requirement: Router slug is explicit, with verbatim class-name fallback

A `Router` instance's `slug` MUST be one of, in order of precedence: the `name=` constructor argument, the class-level `name` attribute, or `type(self).__name__` verbatim. No string transformations (no suffix stripping, no case conversion, no character substitution) are permitted.

#### Scenario: Constructor name takes precedence
- **WHEN** `Router(name="tasks")` is instantiated on a class with `name = "X"`
- **THEN** `instance.slug == "tasks"`

#### Scenario: Class attribute used when no constructor name
- **WHEN** `class R(Router): name = "tasks"` is instantiated with no args
- **THEN** `instance.slug == "tasks"`

#### Scenario: Class name verbatim when nothing set
- **WHEN** `class TasksRouter(Router): pass` is instantiated with no args
- **THEN** `instance.slug == "TasksRouter"` (not "tasks", not "task")

### Requirement: Framework code SHALL NOT use silent fallbacks for introspection failures

When the framework introspects a runtime object (`get_type_hints`, `TypeAdapter(...).json_schema()`, decorator metadata access) and the introspection raises, the framework SHALL either:

- Emit a WARN log line naming the target and the exception class
  before returning a sentinel value (`None` is acceptable when the
  caller has a documented fallback), OR
- Re-raise with an action-oriented message.

The framework SHALL NOT silently absorb an exception and return a
value indistinguishable from a legitimate empty result. The
`_WARN_ONCE` pattern (per-target dedup) SHALL be used to keep log
noise bounded for repeated decoration failures.

#### Scenario: TypeAdapter failure emits a WARN log

- **GIVEN** a tool decorated with `@a2kit.read(reports=Unschemable)` where `Unschemable` cannot be introspected
- **WHEN** the decorator runs
- **THEN** the decoration succeeds (does not raise) AND a WARN log line is emitted naming `Unschemable` and the underlying exception class

#### Scenario: Repeated decoration failures dedup their WARN logs

- **GIVEN** two tools both using the same unschemable report type
- **WHEN** both decorators run
- **THEN** the WARN log fires exactly once for that report-type qualname

### Requirement: Constructors SHALL validate against the declared parameter set

`App.__init__` and `Router.__init__` SHALL accept exactly their
documented keyword parameters. Any unknown kwarg SHALL raise
`TypeError` at construction with a message naming the unknown
key(s) and pointing at the project CHANGELOG for the removal record.

The standard pattern is `**_kw: Any` after the documented
parameters, with an explicit guard:

```python
def __init__(self, name: str, *, lifespan=None, debug=False, **_kw):
    if _kw:
        raise TypeError(
            f"Unexpected kwargs: {sorted(_kw)}. "
            f"See CHANGELOG.md for removals across versions."
        )
```

#### Scenario: Unknown kwarg raises TypeError with hint

- **GIVEN** `a2kit.App("name", health_tool=True)` after `health_tool=` is removed
- **WHEN** the constructor evaluates
- **THEN** `TypeError` is raised
- **AND** the message names `health_tool` and references the CHANGELOG

#### Scenario: Documented kwargs continue to work

- **GIVEN** `a2kit.App("name", lifespan=cm, debug=True)`
- **WHEN** the constructor evaluates
- **THEN** the App constructs successfully (no TypeError)

### Requirement: Framework code SHALL NOT use defensive `hasattr` against framework-typed objects

Code paths that receive framework-internal types (`App`, `Router`, `Container`, `TestClient`, etc., where the type is declared on the parameter or attribute) SHALL access framework attributes directly.
`hasattr` checks against these types SHALL NOT appear except at
genuine protocol boundaries (e.g. duck-typing third-party objects
like `fastmcp.Context` against multiple FastMCP return shapes).

When a framework type might be `None` (legitimate optionality),
narrow with `if x is not None` — not with `hasattr(x, "expected_attr")`.

#### Scenario: hasattr against framework-internal types absent

- **WHEN** `grep -rn 'hasattr(app,' src/a2kit/ --include='*.py'` runs (excluding documented duck-typing boundaries)
- **THEN** the result is empty

#### Scenario: hasattr against fastmcp.Context return shapes still permitted

- **GIVEN** code in `src/a2kit/packages/testing/client.py` discriminates among `result.content` / `result.data` / `result.structured_content`
- **WHEN** that code uses `hasattr`
- **THEN** it is permitted (fastmcp returns different shapes for different surfaces; this is a true protocol boundary)

