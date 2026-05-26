## MODIFIED Requirements

### Requirement: Dispatch stages MUST read Principal via the named bridge

Stages in the dispatch pipeline (`DispatchHookStage`, `AuthorizeGateStage`, `LddStateStage`, and any future stage) SHALL read `Principal` only through the named bridge function `current_request_principal()` (from `a2kit.packages.dispatch._principal_bridge`) and SHALL publish it to the per-call DI scope via `Container.seed_scoped(Principal, p)`. Direct reads of the underlying ContextVar from stage code are forbidden. This requirement SHALL be enforced structurally: only `_principal_bridge.py` MUST import the raw symbol.

#### Scenario: DispatchHookStage uses the bridge and seed_scoped

- **GIVEN** a substrate middleware has called `set_request_principal(p)`
- **WHEN** `DispatchHookStage._wrapped` runs and opens a child
  container
- **THEN** the stage's wire code reads `p` via
  `current_request_principal()`
- **AND** publishes it via `child.seed_scoped(Principal, p)`
- **AND** the stage's source contains no
  `_a2kit_request_principal.get()` or
  `_request_principal.get()` call

#### Scenario: AuthorizeGateStage uses the bridge and seed_scoped

- **GIVEN** a tool with `authorize=lambda *, principal: ...`
- **WHEN** `AuthorizeGateStage` resolves the gate's parameters
- **THEN** Principal is read via `current_request_principal()` and
  seeded via `child.seed_scoped(Principal, p)`
- **AND** the kwargs-by-name `principal` fallback is absent
- **AND** the stage's source contains no direct contextvar read

#### Scenario: Structural enforcement — only the bridge imports the ContextVar

- **WHEN** every module under `a2kit/packages/` (recursively) is
  scanned for imports of the underlying Principal ContextVar
- **THEN** the only file with such an import is
  `a2kit/packages/dispatch/_principal_bridge.py`
- **AND** all other writers and readers use the named functions
  `set_request_principal`, `reset_request_principal`,
  `current_request_principal`
