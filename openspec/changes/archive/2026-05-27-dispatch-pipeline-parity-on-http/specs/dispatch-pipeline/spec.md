## MODIFIED Requirements

### Requirement: Both transports fold the same dispatch pipeline

The CLI adapter, the MCP adapter, **and the HTTP adapter** MUST each build their per-tool dispatch chain by folding the single shared `DISPATCH_PIPELINE`. None of the adapters may carry its own copy of a transport-neutral dispatch concern.

The HTTP adapter SHALL fold the pipeline inside `packages/http/build.py:build_http_app` per projection tool, immediately after `install_substrate_signature` produces the substrate-shaped wrapper. The pipeline SHALL run inside the per-request `Container.call_scope` context so `AuthorizeGateStage` resolves its dependencies through the same DI path as on CLI and MCP.

#### Scenario: MCP adapter folds the shared pipeline

- **WHEN** `mcp/server.py::_build_one_tool` builds a tool's chain
- **THEN** it folds `DISPATCH_PIPELINE` and appends only the MCP
  error-render stage

#### Scenario: CLI adapter folds the shared pipeline

- **WHEN** the CLI builds a tool's dispatch chain
- **THEN** it folds `DISPATCH_PIPELINE` and appends only the CLI
  error-render stage

#### Scenario: HTTP adapter folds the shared pipeline

- **WHEN** `http/build.py::build_http_app` installs a projection tool
- **THEN** the per-tool wrapper folds `DISPATCH_PIPELINE` and appends only the HTTP error-render stage
- **AND** the HTTP wrapper contains no per-route authorize-gate wrapper of its own
- **AND** `AuthorizeGateStage` runs from the folded pipeline on every HTTP projection-tool call

#### Scenario: no duplicated dispatch concern remains

- **WHEN** `packages/cli`, `packages/mcp`, and `packages/http` are inspected
- **THEN** none defines a timeout, ldd-state, enricher,
  dispatch-hook, router-lazy-enter, or authorize-gate wrapper of its own
- **AND** `_apply_authorize_gate` is absent from `packages/http/build.py`
