# verb-decorators — prune-dead-decorator-surface delta

## MODIFIED Requirements

### Requirement: Verb decorators accept MCP annotation kwargs

Verb decorators SHALL accept the semantic-flag kwargs
(`idempotent`, `open_world`, `destructive`, `title`) and the
routing kwargs (`name`, `reports`). Verb decorators SHALL NOT
accept a `tags=` kwarg; framework-derived tags (`"read"`,
`"write"`, `"list"`) are stamped automatically and are not
author-configurable.

#### Scenario: `tags=` kwarg is removed
- **WHEN** a tool is decorated `@a2kit.read(tags={"custom"})`
- **THEN** Python raises `TypeError` (unexpected keyword argument)

#### Scenario: Auto-stamped verb tags still appear
- **WHEN** a tool is decorated `@a2kit.read()`
- **THEN** `meta.tags == frozenset({"read"})`

## REMOVED Requirements

### Requirement: Capabilities map to FastMCP `tags`

The capability registry MUST be removed entirely. `a2kit.Cap` and
`a2kit.capabilities` SHALL NOT exist after this change.

#### Scenario: Capability surface gone
- **WHEN** `import a2kit; a2kit.Cap` is evaluated
- **THEN** `AttributeError` is raised

#### Scenario: Migration is delete-only
- **WHEN** a consumer imports `from a2kit import Cap`
- **THEN** the import fails and the consumer deletes the import (no replacement is needed)
