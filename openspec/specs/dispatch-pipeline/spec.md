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

### Requirement: Dispatch stages read request-scoped values via `request_scope.get(T)`

Stages in the dispatch pipeline (`DispatchHookStage`, `AuthorizeGateStage`, `LddStateStage`, and any future stage) SHALL read request-scoped values exclusively via `a2kit.packages.context.request_scope.get(T)` (or `try_get(T)` where absence is valid). The previous per-type bridge modules and named-API helpers (e.g. `_principal_bridge.set_request_principal`, `_LDD_STATE.get()`) have been removed. The FastAPI `Depends` bridge keeps reading from a DI-package-local ContextVar (the http middleware dual-writes) to preserve `di-container-package`'s standalone-shippability invariant.

#### Scenario: DispatchHookStage reads Principal via request_scope

- **GIVEN** substrate middleware has called `request_scope.publish(principal)`
- **WHEN** `DispatchHookStage._wrapped` runs and opens a child container
- **THEN** the stage threads `Principal` into `Container.call_scope` via `framework_seeds=request_scope.all_seeds()`
- **AND** the stage's source contains no `current_request_principal_seeds()` call

#### Scenario: LddStateStage reads LddState via request_scope

- **WHEN** a tool body calls `event(...)` inside a dispatched call
- **THEN** the LDD primitive reads its state via `request_scope.try_get(_LddState)`
- **AND** outside any dispatched call the primitive raises `AmbientContextMissing` chained from `RequestScopeMissing(_LddState)`

### Requirement: `Container.call_scope` accepts `framework_seeds=` (rename)

`Container.call_scope` SHALL accept a `framework_seeds: dict[type, Any] | None = None` parameter sourced from `request_scope.all_seeds()`. The prior `scoped_seeds=` keyword has been removed.

The rename clarifies the tier split: `framework_seeds` is for framework-tier published values (Principal, LddState, per-request Container). App-author seeds continue to flow through `pre_hook`'s `seed: SeedFn` parameter (the user tier).

#### Scenario: framework_seeds is the documented parameter

- **WHEN** dispatch pipeline code opens a child scope
- **THEN** the call site is `container.call_scope(framework_seeds=request_scope.all_seeds(), ...)`

#### Scenario: scoped_seeds keyword is removed

- **GIVEN** code calling `container.call_scope(scoped_seeds={...})`
- **WHEN** the call runs
- **THEN** Python raises `TypeError: got an unexpected keyword argument 'scoped_seeds'`
- **AND** there is no remaining alias

