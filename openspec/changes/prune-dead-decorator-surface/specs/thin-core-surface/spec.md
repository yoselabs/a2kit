# thin-core-surface — prune-dead-decorator-surface delta

## MODIFIED Requirements

### Requirement: a2kit does not re-export external library symbols

The top-level `a2kit.*` namespace SHALL re-export only first-party
symbols. It SHALL NOT include `a2kit.Cap` or `a2kit.capabilities`
(removed). It SHALL NOT carry an `App(debug=...)` constructor
parameter (removed; the attribute had zero readers).

#### Scenario: `a2kit.Cap` no longer importable
- **WHEN** `import a2kit; a2kit.Cap` is evaluated
- **THEN** `AttributeError` is raised

#### Scenario: `App(debug=...)` rejected
- **WHEN** `a2kit.App("x", debug=True)` is constructed
- **THEN** `TypeError` is raised (unexpected keyword argument)
