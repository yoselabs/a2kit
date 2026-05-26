## ADDED Requirements

### Requirement: The principal bridge is a private dispatch-layer module

The framework SHALL carry per-request `Principal` between substrate
authentication boundaries and the per-call DI scope opening through
a single named bridge module:
`a2kit.packages.dispatch._principal_bridge`. The module is private
(`_`-prefixed) and lives in the dispatch layer (L4). The underlying
`contextvars.ContextVar` instance is module-private and MUST NOT be
re-exported through any `__all__` or package front door.

#### Scenario: Bridge module exists at the canonical path

- **WHEN** importing `a2kit.packages.dispatch._principal_bridge`
- **THEN** the module exposes `set_request_principal`,
  `reset_request_principal`, and `current_request_principal` as
  callable names
- **AND** the module's `__all__` lists exactly these three names

#### Scenario: ContextVar is not re-exported

- **WHEN** inspecting `a2kit.packages.context` and its public surface
- **THEN** no attribute named `_a2kit_request_principal` (or any
  other Principal-carrying ContextVar) appears in `__all__`
- **AND** `from a2kit.packages.context import _a2kit_request_principal`
  raises `ImportError` (the symbol was removed)

### Requirement: Named writer API for substrate adapters

Substrate adapters that authenticate a request SHALL publish
`Principal` via the named bridge writer API. They MUST NOT import
the underlying ContextVar directly.

`set_request_principal(p: Principal) -> Token` publishes `p` for the
current async context, returning a `Token` that callers MUST pass to
`reset_request_principal(token: Token) -> None` in a `finally` block.

#### Scenario: A substrate writer publishes Principal via the named API

- **GIVEN** a substrate middleware that has authenticated a request
- **WHEN** the middleware calls `set_request_principal(p)` and then
  invokes downstream dispatch
- **THEN** `current_request_principal()` inside the downstream
  dispatch returns `p`
- **AND** the writer's source contains no reference to the raw
  ContextVar by name

#### Scenario: Reset restores prior state

- **GIVEN** `set_request_principal(p1)` was called producing `token1`
- **WHEN** another async task in the same context calls
  `set_request_principal(p2)` (producing `token2`) and then
  `reset_request_principal(token2)`
- **THEN** `current_request_principal()` returns `p1`
- **AND** subsequent `reset_request_principal(token1)` restores the
  pre-`p1` state (`None` if there was no prior set)

### Requirement: Reader API for dispatch stages

Dispatch stages that need `Principal` SHALL read it via
`current_request_principal()` returning `Principal | None`. The reader
returns `None` when no substrate has published a Principal for the
current context (unauthenticated transport).

#### Scenario: Reader returns None outside a request

- **GIVEN** no substrate has called `set_request_principal`
- **WHEN** `current_request_principal()` is invoked
- **THEN** it returns `None`

#### Scenario: Stages use the reader, not the raw ContextVar

- **WHEN** the source of any module under
  `a2kit/packages/dispatch/stages.py`,
  `a2kit/packages/dispatch/substrate.py`,
  `a2kit/packages/auth/`,
  `a2kit/packages/mcp/`,
  `a2kit/packages/http/` is scanned
- **THEN** no module other than `_principal_bridge` references the
  raw ContextVar name `_request_principal` directly
- **AND** all reads happen through `current_request_principal()`
- **AND** all writes happen through `set_request_principal` /
  `reset_request_principal`

### Requirement: Structural enforcement replaces grep-based enforcement

The grep-based stage-source test from `principal-single-source` SHALL be retired in favor of import-path discipline: only `_principal_bridge.py` MUST import the underlying ContextVar; the file structure prevents accidental re-introduction in stage code.

#### Scenario: The grep-based stage-source test is retired

- **WHEN** the test suite is inspected
- **THEN** no test asserts "stages.py contains no `_a2kit_request_principal`"
- **AND** the equivalent guarantee is provided by the bridge module
  being the only path to the ContextVar
