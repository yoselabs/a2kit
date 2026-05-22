# core-purity Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: Verb decorators carry no feature kwargs

`@a2kit.read`, `@a2kit.write`, and `@a2kit.list_` MUST accept only the documented annotation keyword arguments and MUST NOT accept feature kwargs such as `enricher=` or `report=`. Other behavior is attached via stacked feature decorators where such decorators exist. The bare `@a2kit.tool` verb does not exist (removed in v0.33); this requirement covers only `read`, `write`, and `list_`.

#### Scenario: Reject enricher kwarg

- **WHEN** code calls `@a2kit.read(enricher=fn)`
- **THEN** Python raises `TypeError` for the unexpected keyword argument

#### Scenario: Reject report kwarg

- **WHEN** code calls `@a2kit.read(report=MyReport)`
- **THEN** Python raises `TypeError`

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

