## ADDED Requirements

### Requirement: The substrate-to-pipeline bridge uses exactly two ContextVars

Substrate adapters (HTTP, MCP, CLI, and any future substrate) SHALL communicate with the transport-neutral `DISPATCH_PIPELINE` via exactly two named ContextVars and no other side-channels:

- `a2kit.packages.context.request_scope` — the **inbound** seed channel. Substrate populates per-call typed values (currently `Principal`); pipeline stages read them via `request_scope.get(T)` / `try_get(T)` and thread them into `Container.call_scope` via `framework_seeds=request_scope.all_seeds()`.
- `a2kit.packages.dispatch._render_state` — the **outbound** render channel. `ErrorEnvelopeStage` writes the rendered prose + envelope dict here keyed by `id(exc)`; the per-substrate error-render stage reads it after the pipeline raises and converts to substrate-native wire shape.

A substrate adapter SHALL NOT define its own per-call ContextVar for cross-pipeline communication. The two named channels are the contract; new cross-cutting needs are met by extending what the existing channels carry (typed seeds for `request_scope`; the `RenderedError` record for `_render_state`), not by adding parallel channels.

#### Scenario: Pipeline stages do not import substrate-specific modules

- **WHEN** any module under `a2kit.packages.dispatch.` is inspected
- **THEN** it imports neither `fastapi`, `starlette`, nor `fastmcp`
- **AND** any per-call value it consumes is read via `request_scope.get(T)` or `request_scope.try_get(T)`

#### Scenario: Substrate adapters do not reach past the two named channels

- **WHEN** `a2kit.packages.http` and `a2kit.packages.mcp` are inspected for ContextVars that cross the pipeline boundary
- **THEN** the only contextvars they read or write are `request_scope` and `_render_state`
- **AND** no `ContextVar` declared inside `packages/http` or `packages/mcp` is read by any module under `packages/dispatch`

### Requirement: Every substrate seeds `request_scope` before folding the pipeline

For every registered substrate that exposes tool calls (HTTP, MCP, CLI, future), the substrate's per-call entry path SHALL `request_scope.publish(value)` for every typed seed it owns BEFORE control reaches `fold_pipeline` for the tool. The publish/reset pair SHALL bracket the pipeline call in a `try`/`finally` so the contextvar is reset whether the pipeline returned normally or raised.

`Principal` is the only typed seed defined by the framework today; future seeds (e.g. `RequestId`, `Tenant`) follow the same protocol.

#### Scenario: HTTP middleware publishes Principal before the pipeline runs

- **GIVEN** an HTTP request whose auth path resolves a `Principal`
- **WHEN** the per-tool wrapper is invoked
- **THEN** `request_scope.get(Principal)` returns the resolved Principal during pipeline execution
- **AND** after the wrapper returns or raises, the publish token is reset in a `finally` block

#### Scenario: MCP middleware publishes Principal before the pipeline runs

- **GIVEN** an MCP `tools/call` whose context carries a `Principal`
- **WHEN** the per-tool wrapper is invoked
- **THEN** `request_scope.get(Principal)` returns the resolved Principal during pipeline execution
- **AND** after the wrapper returns or raises, the publish token is reset in a `finally` block

#### Scenario: Capability test enumerates registered substrates

- **WHEN** the capability test under `tests/capabilities/substrate_pipeline_bridge/` runs
- **THEN** it asserts each registered surface (`api`, `mcp`) has a known principal-publishing seam wired before its `fold_pipeline` call
- **AND** a future surface registered without the seam fails the test

### Requirement: Every substrate reads `_render_state` after the pipeline raises

For every registered substrate, when the folded pipeline raises a `CapturedError` (or any subclass), the substrate's per-tool wrapper SHALL retrieve the rendered envelope from `_render_state` via `get_rendered_error(exc) -> RenderedError | None` and render it to substrate-native wire shape. The substrate SHALL NOT re-derive the `AppError → kind → status` mapping itself.

A defensive fallback is permitted when `get_rendered_error` returns `None` (e.g., an unexpected path bypassed `ErrorEnvelopeStage`); the fallback SHALL be inline-documented as defensive-only and SHALL still emit the typed envelope shape.

#### Scenario: HTTP error-render stage reads from `_render_state`

- **GIVEN** a tool body that raised `NotFound(...)` and the pipeline propagated `CapturedError`
- **WHEN** the HTTP per-tool wrapper handles the captured error
- **THEN** it calls `get_rendered_error(exc)` to retrieve the `RenderedError`
- **AND** the response body is `{"error": <envelope>}` from that `RenderedError`
- **AND** the HTTP wrapper contains no `AppError → status` lookup of its own

#### Scenario: MCP error-render stage reads from `_render_state`

- **GIVEN** a tool body that raised `NotFound(...)` and the pipeline propagated `CapturedError`
- **WHEN** the MCP per-tool wrapper handles the captured error
- **THEN** it calls `get_rendered_error(exc)` and forwards the prose + envelope to the FastMCP middleware
- **AND** the MCP wrapper contains no `AppError → kind → ToolError` lookup of its own

### Requirement: The bridge contract is enforced by a capability test, not a Protocol

The substrate-to-pipeline bridge SHALL be enforced by a capability test under `tests/capabilities/substrate_pipeline_bridge/` that walks every registered substrate and asserts the seed/read contract is honoured. No `SubstrateBridge` `Protocol` class SHALL be introduced at this time; the contract lives as documentation + capability test until a third substrate exercises it.

When a third substrate is added, the change introducing it SHALL evaluate whether to promote the contract to a Protocol; until then, the capability test is the regression net.

#### Scenario: No SubstrateBridge Protocol exists

- **WHEN** `grep -rn "class SubstrateBridge" src/a2kit/` runs
- **THEN** the output is empty

#### Scenario: Capability test exists and is wired

- **WHEN** `tests/capabilities/substrate_pipeline_bridge/` is inspected
- **THEN** at least one test asserts the seed contract for every registered substrate
- **AND** at least one test asserts the read-render contract for every registered substrate
