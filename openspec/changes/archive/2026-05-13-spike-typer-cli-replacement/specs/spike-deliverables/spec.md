# spike-deliverables — spike-typer-cli-replacement delta

## ADDED Requirements

### Requirement: A research spike SHALL produce a written decision artifact

A change classified as a research spike (no production code) SHALL
produce a `design.md` containing (a) one paragraph of findings per
declared sub-question, and (b) a single closing decision line of
the form "Decision: proceed to <follow-up-change-id>." or
"Decision: rejected. Rationale: <reason>." The spike SHALL NOT be
considered complete until the decision line is filled in. An empty
or placeholder decision line means the spike has not delivered.

#### Scenario: Decision line populated on proceed

- **GIVEN** a spike change whose `design.md` contains paragraphs
  for every declared sub-question and a closing line
  "Decision: proceed to replace-cli-builder-with-typer."
- **WHEN** the spike is archived
- **THEN** the archive succeeds and the referenced follow-up
  change id is logged for tracking

#### Scenario: Decision line populated on reject

- **GIVEN** a spike change whose `design.md` contains paragraphs
  for every declared sub-question and a closing line
  "Decision: rejected. Rationale: Q3 forces double-encoding
  through click.echo."
- **WHEN** the spike is archived
- **THEN** the archive succeeds and the rationale is preserved
  for future readers who form the same hypothesis

#### Scenario: Spike with placeholder decision is incomplete

- **GIVEN** a spike change whose `design.md` "Decision" line
  still reads "[One of: ...]" or is otherwise unfilled
- **WHEN** any reader checks the change's status
- **THEN** the change is reported as incomplete and SHALL NOT be
  archived
