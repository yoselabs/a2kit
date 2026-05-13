# thin-core-surface — trim-top-level-namespace delta

## MODIFIED Requirements

### Requirement: a2kit does not re-export external library symbols

The top-level `a2kit.*` namespace SHALL re-export only the 95%-flow
authoring surface. Introspection types, plugin-author types, and
non-umbrella exception classes SHALL live in their owning modules
and SHALL NOT be re-exported at top-level.

Kept at top-level: `App`, `Router`, `run`, `read`, `write`,
`list_`, `tool`, `ToolContext`, `HealthResult`, `A2KitError`,
plus the `visibility` Literal alias if one is exported.

Demoted (removed from top-level; still importable from owning
modules):
`A2KitMeta` → `a2kit.metadata`,
`RouterRegistry` → `a2kit.routers`,
`UNRESOLVED` → `a2kit.app`,
`ToolCallContamination`, `InvalidToolReturnTypeError`,
`InvalidFilterExpression`, `ReportTypeNotDeclared`,
`ReportTypeMismatch` → `a2kit.exceptions`.

LDD sink-author types (`LddEmission`, `LddSink`, `format_ldd_line`,
`ldd_state_for_call`) SHALL be removed from the `a2kit.ldd`
top-level re-export; authors who need them import from
`a2kit.packages.ldd` (or a future `a2kit.ldd.sinks` submodule).

#### Scenario: Demoted symbols are not at top-level
- **WHEN** `import a2kit; a2kit.A2KitMeta` is evaluated
- **THEN** `AttributeError` is raised

#### Scenario: Demoted symbols importable from owning modules
- **WHEN** `from a2kit.metadata import A2KitMeta` is evaluated
- **THEN** the import succeeds and the class is returned

#### Scenario: `A2KitError` remains at top-level
- **WHEN** `from a2kit import A2KitError` is evaluated
- **THEN** the import succeeds (umbrella exception is kept)

#### Scenario: Live LDD author surface unchanged
- **WHEN** `from a2kit.ldd import event, report, log, info` is evaluated
- **THEN** the import succeeds (live primitives remain re-exported)

#### Scenario: Sink-author types removed from a2kit.ldd
- **WHEN** `from a2kit.ldd import LddSink` is evaluated after this change
- **THEN** `ImportError` is raised (sink-author types moved to `a2kit.packages.ldd` or `a2kit.ldd.sinks`)
