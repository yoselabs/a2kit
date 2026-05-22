# app-builder-runtime Specification

## Purpose
TBD - created by archiving change split-app-builder-runtime. Update Purpose after archive.
## Requirements
### Requirement: Composition happens on a mutable AppBuilder

`a2kit.AppBuilder` MUST be the mutable composition surface. It exposes
`add_router`, `add_cli`, `add_mcp_middleware`, `provide`, and
`health_check`. Each composition verb returns the `AppBuilder` for
chaining.

#### Scenario: builder verbs chain

- **WHEN** user calls
  `AppBuilder("svc").add_router(r).provide(Store)`
- **THEN** each call returns the same `AppBuilder` instance

#### Scenario: build yields a sealed App

- **WHEN** user calls `AppBuilder("svc").build()`
- **THEN** the result is an `a2kit.App` instance

### Requirement: The built App is a mutation-free runtime

`a2kit.App` MUST expose only the runtime surface — `tools()`,
`routers()`, `container()`, the async-context-manager protocol, and the
LDD kill-switch. It MUST NOT expose any composition verb
(`add_router`, `add_cli`, `add_mcp_middleware`, `provide`,
`health_check`).

#### Scenario: App has no composition verb

- **WHEN** code calls `app.add_router(r)` on a built `App`
- **THEN** it raises `TypeError` with a migration hint naming
  `AppBuilder`

#### Scenario: App is still an async context manager

- **WHEN** a built `App` is used as `async with app:`
- **THEN** it enters and exits its lifecycle as before the split

### Requirement: build() is the seal point

`AppBuilder.build()` MUST construct the DI container, validate the
provider graph, auto-install the `_meta.health` router when health
checks were registered, and return the sealed `App`. After `build()`,
the `AppBuilder` MUST NOT be usable to mutate the produced `App`.

#### Scenario: provider graph validated at build

- **WHEN** `build()` runs on a builder whose app-scope factory depends
  on a per-call type
- **THEN** `build()` raises, reporting the offending provider edge

#### Scenario: health router installed at build

- **WHEN** a builder has at least one `health_check` registered and
  `build()` is called
- **THEN** the resulting `App.routers()` includes the `_meta` router

### Requirement: Direct App construction is rejected with a migration hint

Constructing `a2kit.App` directly MUST raise `TypeError` naming
`AppBuilder` and the `AppBuilder(...).build()` call shape. No alias and
no deprecation window are provided.

#### Scenario: direct App construction raises

- **WHEN** code runs `a2kit.App("svc")`
- **THEN** it raises `TypeError` whose message names
  `AppBuilder("svc").build()`

### Requirement: Test overrides happen by re-build, not post-seal mutation

Swapping a service for a fake in tests MUST be done by re-registering
it on an `AppBuilder` (`provide`, last-write-wins) and calling
`build()`. The framework MUST NOT provide a mechanism to override a
sealed container after `build()` — `Container._override` / `_snapshot`
/ `_restore`, `App._test_override_owner`, and `TestClient.override()`
MUST NOT exist.

#### Scenario: re-registered fake wins

- **WHEN** a test calls `builder.provide(LLM, RealLLM)` then
  `builder.provide(LLM, StubLLM)` and `build()`s
- **THEN** the resulting `App` resolves `LLM` to `StubLLM`

#### Scenario: no post-seal override surface remains

- **WHEN** `packages/di/container.py` and `packages/testing/client.py`
  are inspected
- **THEN** they define no `_override`, `_snapshot`, `_restore`, or
  `override` test-seam member

#### Scenario: old TestClient.override raises a migration hint

- **WHEN** test code calls `TestClient.override(...)`
- **THEN** it raises with a hint to build a fresh `App` from an
  `AppBuilder` with the fake `provide`d

