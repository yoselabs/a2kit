# thin-core-surface — prune-dead-decorator-surface delta

## MODIFIED Requirements

### Requirement: a2kit does not re-export external library symbols

The top-level `a2kit.*` namespace SHALL re-export only first-party
symbols. It SHALL NOT include `a2kit.Cap` or `a2kit.capabilities`
(removed).

#### Scenario: `a2kit.Cap` no longer importable
- **WHEN** `import a2kit; a2kit.Cap` is evaluated
- **THEN** `AttributeError` is raised

#### Scenario: `a2kit.capabilities` no longer importable
- **WHEN** `import a2kit; a2kit.capabilities` is evaluated
- **THEN** `AttributeError` is raised

## REMOVED Requirements

### Requirement: Capabilities map to FastMCP `tags`

The capability registry SHALL be removed entirely. `a2kit.Cap` and
`a2kit.capabilities` SHALL NOT exist after this change.

#### Scenario: Capability surface gone
- **WHEN** `import a2kit; a2kit.Cap` is evaluated
- **THEN** `AttributeError` is raised
