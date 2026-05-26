## MODIFIED Requirements

### Requirement: Dispatch stages read request-scoped values via `request_scope.get(T)`

Stages in the dispatch pipeline (`DispatchHookStage`, `AuthorizeGateStage`, `LddStateStage`, and any future stage) SHALL read request-scoped values exclusively via `a2kit.packages.dispatch.request_scope.get(T)` (or `try_get(T)` where absence is valid). Per-type bridge readers (e.g. `current_request_principal_seeds()`, `_LDD_STATE.get()`, `_a2kit_request_scope.get()`) SHALL be deprecation shims for one release, then removed.

#### Scenario: DispatchHookStage reads Principal via request_scope

- **GIVEN** substrate middleware has called `request_scope.publish(principal)`
- **WHEN** `DispatchHookStage._wrapped` runs and opens a child container
- **THEN** the stage reads `principal` via `request_scope.get(Principal)`
- **AND** seeds it via `child.seed_scoped(Principal, principal)`
- **AND** the stage's source contains no `current_request_principal_seeds()` call

#### Scenario: LddStateStage reads LddState via request_scope

- **WHEN** a tool body calls `event(...)` inside a dispatched call
- **THEN** the LDD primitive reads its state via `request_scope.get(LddState)`
- **AND** outside any dispatched call the primitive raises `RequestScopeMissing(LddState)`

### Requirement: `Container.call_scope` accepts `framework_seeds=` (rename)

`Container.call_scope` SHALL accept a `framework_seeds: dict[type, Any] | None = None` parameter sourced from `request_scope.all_seeds()`. The prior `scoped_seeds=` keyword SHALL be accepted for one release as a deprecation-shim alias forwarding to `framework_seeds=`, emitting `DeprecationWarning`.

The rename clarifies the tier split: `framework_seeds` is for framework-tier published values (Principal, LddState, per-request Container). App-author seeds continue to flow through `pre_hook`'s `seed: SeedFn` parameter (the user tier).

#### Scenario: framework_seeds is the documented parameter

- **WHEN** dispatch pipeline code opens a child scope
- **THEN** the call site is `container.call_scope(framework_seeds=request_scope.all_seeds(), ...)`

#### Scenario: scoped_seeds emits DeprecationWarning

- **GIVEN** out-of-tree code calling `container.call_scope(scoped_seeds={...})`
- **WHEN** the call runs
- **THEN** `DeprecationWarning` is emitted pointing at `framework_seeds=`
- **AND** the call still succeeds with identical semantics
