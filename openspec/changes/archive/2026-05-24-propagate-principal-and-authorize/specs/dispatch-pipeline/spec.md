## ADDED Requirements

### Requirement: `AuthorizeGateStage` is part of `DISPATCH_PIPELINE`

`DISPATCH_PIPELINE` SHALL include `AuthorizeGateStage` immediately after `DispatchHookStage` (so wire-side resolution and `call_scope` are both ready) and immediately before the tool body. The stage SHALL self-skip when the descriptor's `authorize is None`. When `authorize` is set, the stage SHALL resolve the callable's parameters through `call_scope` and invoke it; a falsy return SHALL raise `AuthorizationDenied`.

#### Scenario: pipeline order is fixed

- **GIVEN** any descriptor with `authorize=` set
- **WHEN** `DISPATCH_PIPELINE` is inspected
- **THEN** the position index of `AuthorizeGateStage` is greater than `DispatchHookStage`'s
- **AND** strictly less than the tool-body stage's

#### Scenario: skip is zero-cost when authorize unset

- **GIVEN** a descriptor with `authorize is None`
- **WHEN** the stage runs
- **THEN** it returns without invoking any callable or touching `call_scope`
