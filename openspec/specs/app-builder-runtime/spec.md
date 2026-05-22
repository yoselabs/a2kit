# app-builder-runtime Specification

## Purpose
TBD - created by archiving change split-app-builder-runtime. Update Purpose after archive.
## Requirements
### Requirement: Test overrides happen by re-build, not post-seal mutation

Swapping a service for a fake in tests MUST be done by constructing a
fresh `a2kit.App`, registering the fake with `provide` (last-write-wins),
and handing that `App` to a finisher. The framework MUST NOT provide a
mechanism to override a sealed container — `Container._override` /
`_snapshot` / `_restore`, an `App` test-override-owner flag, and
`TestClient.override()` MUST NOT exist.

#### Scenario: re-registered fake wins

- **WHEN** a test calls `app.provide(LLM, RealLLM)` then
  `app.provide(LLM, StubLLM)` on a fresh `App`
- **THEN** the sealed `App` resolves `LLM` to `StubLLM`

#### Scenario: no post-seal override surface remains

- **WHEN** `packages/di/container.py` and `packages/testing/client.py`
  are inspected
- **THEN** they define no `_override`, `_snapshot`, `_restore`, or
  `override` test-seam member

#### Scenario: old TestClient.override raises a migration hint

- **WHEN** test code calls `TestClient.override(...)`
- **THEN** it raises with a hint to construct a fresh `App` with the
  fake `provide`d

### Requirement: Composition happens on a mutable App

`a2kit.App` MUST be the single public composition type. It is
constructed directly (`a2kit.App("svc")`) and exposes the composition
verbs `add_router`, `add_cli`, `add_mcp_middleware`, `provide`, and
`health_check`. Each composition verb returns the `App` for chaining.

#### Scenario: App is constructed directly

- **WHEN** user calls `a2kit.App("svc")`
- **THEN** an `a2kit.App` instance is returned with no error

#### Scenario: composition verbs chain

- **WHEN** user calls `a2kit.App("svc").add_router(r).provide(Store)`
- **THEN** each call returns the same `App` instance

### Requirement: The sealed runtime is internal

Sealing MUST NOT produce a consumer-visible type. `a2kit` MUST NOT
export an `AppBuilder` symbol, and `a2kit.App` MUST NOT expose a public
`build()` method. The sealed-runtime representation is a framework
implementation detail.

#### Scenario: AppBuilder is not a public symbol

- **WHEN** user writes `from a2kit import AppBuilder`
- **THEN** the import raises `ImportError`

#### Scenario: App has no public build()

- **WHEN** user inspects `a2kit.App`
- **THEN** there is no public `build` method on the surface

### Requirement: Finishers seal the App

The finishers MUST accept an `a2kit.App` and seal it internally before running, serving, or testing. The finishers are `a2kit.run`, `a2kit.packages.mcp.build_mcp_server`, and `a2kit.testing.client`. Sealing validates the provider graph and locks the DI container. Consumer code MUST NOT be required to call any seal step. Sealing MUST be idempotent, so one `App` may be passed to more than one finisher.

#### Scenario: finisher seals before running

- **WHEN** an `App` whose app-scope factory depends on a per-call type
  is passed to a finisher
- **THEN** the finisher raises, reporting the offending provider edge

#### Scenario: App is reusable across finishers

- **WHEN** the same `App` is passed to two finishers in turn
- **THEN** neither call raises a "spent" or "already sealed" error

### Requirement: Composition after sealing is rejected

A composition verb called on a sealed `App` MUST raise `TypeError` with an action-oriented message. This applies to `add_router`, `add_cli`, `add_mcp_middleware`, `provide`, and `health_check` once a finisher has sealed the `App`.

#### Scenario: provide after a finisher sealed the App

- **WHEN** an `App` has been sealed by a finisher and code then calls
  `app.provide(T, factory)`
- **THEN** it raises `TypeError` explaining the App is sealed

