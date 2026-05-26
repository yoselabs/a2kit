# principal-bridge Specification

## Purpose
Carry the substrate-published :class:`Principal` from authentication
boundary code into the per-call DI scope opened by the dispatch
pipeline. **Subsumed** by the unified
[`request-scope`](../request-scope/spec.md) bridge (per
`generalise-context-bridges`, 2026-05-27). All Principal flow now
travels through the shared `a2kit.packages.context.request_scope`
module — there is no dedicated `_principal_bridge` module.

## Requirements

### Requirement: Principal is published via `request_scope.publish(p)`

Substrate authentication boundary code (`packages/auth/api_key`,
`packages/mcp/principal_middleware`, `packages/http/build`) SHALL
publish the request `Principal` via
`a2kit.packages.context.request_scope.publish(p)` and SHALL reset
via `request_scope.reset(token)` in a `finally` block.

#### Scenario: Middleware publishes and resets

- **GIVEN** a substrate middleware extracts a `Principal` from the request
- **WHEN** the middleware calls `request_scope.publish(p)` and then invokes the downstream chain
- **THEN** `request_scope.get(Principal)` inside the downstream resolves to `p`
- **AND** after `request_scope.reset(token)` runs in the middleware's `finally` block, the lookup falls back to absent for subsequent unrelated requests

### Requirement: Dispatch stages read Principal via `request_scope`

Dispatch stages (`DispatchHookStage`, `AuthorizeGateStage`, future
stages) SHALL thread `Principal` into `Container.call_scope` via
`framework_seeds=request_scope.all_seeds()`. They SHALL NOT name a
per-type Principal reader.

#### Scenario: DispatchHookStage seeds Principal via framework_seeds

- **GIVEN** substrate middleware published a `Principal`
- **WHEN** `DispatchHookStage._wrapped` opens a child container
- **THEN** the stage passes `framework_seeds=request_scope.all_seeds()` to `call_scope`
- **AND** the tool body's `principal: Principal` parameter resolves to the published value
