## ADDED Requirements

### Requirement: Dispatch stages MUST NOT read Principal from a contextvar

No stage in the dispatch pipeline (`DispatchHookStage`, `AuthorizeGateStage`, `LddStateStage`, and any future stage) MAY read `_a2kit_request_principal` or any equivalent contextvar to obtain `Principal`. Stages SHALL resolve `Principal` (or any other typed dependency) through the per-call DI scope only. The kwargs seeding pattern that re-injects Principal after a contextvar read MUST be removed.

#### Scenario: DispatchHookStage resolves Principal from DI

- **GIVEN** a dispatch with a registered DispatchHookStage and a Principal written into the DI scope by the substrate adapter
- **WHEN** the stage's `.wrap()` runs
- **THEN** any Principal needed by the hook is obtained via the DI scope
- **AND** the stage's source contains no `_a2kit_request_principal.get()` call

#### Scenario: AuthorizeGateStage resolves the gate's dependencies via DI only

- **GIVEN** a tool with `authorize=lambda *, principal: ...`
- **WHEN** `AuthorizeGateStage` resolves the gate's parameters
- **THEN** `Principal` is obtained from the DI scope
- **AND** the stage source contains no contextvar-based fallback for Principal
