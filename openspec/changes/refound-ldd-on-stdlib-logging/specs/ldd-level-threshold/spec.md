## MODIFIED Requirements

### Requirement: Level threshold
The level threshold SHALL be expressed as a stdlib logging level applied
once at the emission primitive, before both operator and wire fan-out,
so an accepted emission reaches all handlers and a rejected one reaches
none.

#### Scenario: sub-threshold emission reaches no handler
- **WHEN** an emission's level is below the configured threshold
- **THEN** no handler (operator, wire, or journal) receives it

#### Scenario: accepted emission reaches all handlers
- **WHEN** an emission's level meets or exceeds the threshold
- **THEN** every registered handler receives it
