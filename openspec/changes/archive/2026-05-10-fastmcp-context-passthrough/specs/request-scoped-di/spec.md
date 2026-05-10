## MODIFIED Requirements

### Requirement: Always-provided allowlist for framework types

The container SHALL treat `fastmcp.Context` (re-exported as `a2kit.ToolContext`) and `App` as always-provided: when a tool method declares a kwarg of either type, the framework dispatch hook fills the value without requiring an `App.provide()` registration. Because `a2kit.ToolContext is fastmcp.Context` evaluates to `True`, both annotation styles resolve to the same allowlisted entry.

#### Scenario: ToolContext is filled implicitly
- **GIVEN** a tool method `async def import_tasks(self, *, ctx: a2kit.ToolContext, store: TrackerStore, ...) -> ...`
- **WHEN** the tool is dispatched
- **THEN** `ctx` is bound by the framework (the live `fastmcp.Context` under `serve`, the CLI stub under CLI) and `store` is bound by the container

#### Scenario: fastmcp.Context annotation also allowlisted
- **GIVEN** a tool method `async def t(self, *, ctx: fastmcp.Context) -> dict`
- **WHEN** the tool is dispatched
- **THEN** `ctx` is bound by the framework without requiring an `App.provide(fastmcp.Context, ...)` call

### Requirement: Lint enforces provider availability

Lint rule `A2K-DI-PROVIDER` SHALL fail when any tool method declares an injectable kwarg type that is not registered in the App's container and is not on the always-provided allowlist (`fastmcp.Context` and `App`).

#### Scenario: Missing provider fails lint
- **GIVEN** a router declares a tool with `store: TrackerStore` but the test harness builds an `App` without `provide(TrackerStore, ...)`
- **WHEN** `make lint` runs
- **THEN** `A2K-DI-PROVIDER` reports `TrackerStore` as missing in the app graph

#### Scenario: ctx parameter does not require a provider
- **GIVEN** a tool method declaring only `ctx: a2kit.ToolContext` as an injectable
- **WHEN** `make lint` runs
- **THEN** `A2K-DI-PROVIDER` does not report `fastmcp.Context` as missing
