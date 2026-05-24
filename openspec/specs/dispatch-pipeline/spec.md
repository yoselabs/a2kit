# dispatch-pipeline Specification

## Purpose
TBD - created by archiving change extract-dispatch-pipeline. Update Purpose after archive.
## Requirements
### Requirement: The transport-neutral dispatch pipeline is fastmcp-free

The `a2kit.packages.dispatch` package MUST NOT import `fastmcp` in any
form and MUST NOT appear on the `A2K-IMPORT-DISCIPLINE` fastmcp
allowlist. The five transport-neutral dispatch concerns — enrichers,
ldd-state with ctx synthesis, timeout, dispatch-hook, router-lazy-enter
— MUST be defined there.

#### Scenario: the dispatch package imports no fastmcp

- **WHEN** `a2kit.packages.dispatch` and its submodules are imported
- **THEN** no `fastmcp` module is imported as a result

#### Scenario: the CLI cold path stays fastmcp-free

- **WHEN** the CLI tool-invocation path is exercised
- **THEN** `fastmcp` is not imported

### Requirement: Both transports fold the same dispatch pipeline

The CLI adapter and the MCP adapter MUST each build their per-tool
dispatch chain by folding the single shared `DISPATCH_PIPELINE`. Neither
adapter may carry its own copy of a transport-neutral dispatch concern.

#### Scenario: MCP adapter folds the shared pipeline

- **WHEN** `mcp/server.py::_build_one_tool` builds a tool's chain
- **THEN** it folds `DISPATCH_PIPELINE` and appends only the MCP
  error-render stage

#### Scenario: CLI adapter folds the shared pipeline

- **WHEN** the CLI builds a tool's dispatch chain
- **THEN** it folds `DISPATCH_PIPELINE` and appends only the CLI
  error-render stage

#### Scenario: no duplicated dispatch concern remains

- **WHEN** `packages/cli` and `packages/mcp` are inspected
- **THEN** neither defines a timeout, ldd-state, enricher,
  dispatch-hook, or router-lazy-enter wrapper of its own

### Requirement: The dispatch pipeline is a folded sequence of typed stages

The pipeline MUST be expressed as an ordered tuple of `DispatchStage`
objects, each with a `wrap(fn, spec: ToolBuildSpec) -> fn` method, and
applied by folding. The canonical order MUST live in exactly one
module-level constant with its rationale documented.

#### Scenario: order lives in one constant

- **WHEN** a reader needs the dispatch stage order
- **THEN** `DISPATCH_PIPELINE` is the single authoritative source, and
  a built chain's nesting order matches it

#### Scenario: a stage is unit-tested in isolation

- **WHEN** a test constructs one stage and calls `wrap` with a stub
  `fn` and a `ToolBuildSpec`
- **THEN** the call succeeds without building an MCP server or a CLI
  command

### Requirement: Conditional dispatch stages self-skip

A `DispatchStage` MUST return the input `fn` unchanged when its concern
does not apply to a given tool. The pipeline MUST NOT be filtered or
reordered per tool.

#### Scenario: timeout stage self-skips when unconfigured

- **WHEN** `TimeoutStage.wrap` runs for a tool with no configured
  timeout
- **THEN** it returns the input `fn` unchanged

#### Scenario: router-lazy-enter stage self-skips without `__aenter__`

- **WHEN** `RouterLazyEnterStage.wrap` runs for a router with no
  `__aenter__`
- **THEN** it returns the input `fn` unchanged

### Requirement: Error capture is a neutral stage; error rendering is per-transport

Capturing a tool-body exception into a structured error MUST be a
transport-neutral stage in `packages/dispatch`. Rendering that
structured error to a wire shape MUST be done by the per-transport
adapter — `ToolError(json)` for MCP, an exit-code mapping for the CLI.

#### Scenario: same exception, transport-specific shape

- **WHEN** a tool body raises and the result is taken once through the
  MCP adapter and once through the CLI adapter
- **THEN** the MCP path yields a `ToolError` JSON envelope and the CLI
  path yields the mapped non-zero exit code, both from the one neutral
  capture stage


### Requirement: `AuthorizeGateStage` is part of `DISPATCH_PIPELINE`

`DISPATCH_PIPELINE` SHALL include `AuthorizeGateStage` immediately after
`DispatchHookStage` (so wire-side resolution and `call_scope` are both
ready) and immediately before `LddStateStage`. The stage SHALL
self-skip when the descriptor's `authorize is None`. When `authorize` is
set, the stage SHALL resolve the callable's parameters through
`call_scope` and invoke it; a falsy return SHALL raise
`AuthorizationDenied`.

#### Scenario: pipeline order is fixed

- **GIVEN** any descriptor with `authorize=` set
- **WHEN** `DISPATCH_PIPELINE` is inspected
- **THEN** the position index of `AuthorizeGateStage` is greater than `DispatchHookStage`'s
- **AND** strictly less than `LddStateStage`'s

#### Scenario: skip is zero-cost when authorize unset

- **GIVEN** a descriptor with `authorize is None`
- **WHEN** the stage runs
- **THEN** it returns without invoking any callable or touching `call_scope`
