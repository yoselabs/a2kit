# verb-decorators — adr-semantic-flag-vocabulary delta

## ADDED Requirements

### Requirement: Semantic flags are a locked transport-neutral vocabulary

Four decorator kwargs SHALL form a locked transport-neutral semantic
vocabulary: `idempotent`, `open_world`, `destructive`, `title`. They
MUST NOT be treated as MCP-specific escape hatches. Each flag MUST
have a meaningful read on at least two transports. Any addition to
this vocabulary MUST be captured in an ADR superseding or extending
`docs/adr/0003-semantic-flag-vocabulary.md`.

#### Scenario: Vocabulary is documented in ADR 0003
- **WHEN** a contributor reads `docs/adr/0003-semantic-flag-vocabulary.md`
- **THEN** the ADR enumerates the four flags
- **AND** lists the per-transport read for each (MCP, CLI, REST, GraphQL)
- **AND** documents the contract for adding new flags (two-transport minimum)

#### Scenario: `annotations={...}` collapse is explicitly rejected
- **WHEN** a future audit proposes collapsing the four flags into one `annotations={...}` dict
- **THEN** ADR 0003 names this collapse as the rejected alternative and points at why (would promote MCP to a privileged transport in the surface)
