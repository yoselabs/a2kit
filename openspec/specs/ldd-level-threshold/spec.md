# ldd-level-threshold Specification

## Purpose

Defines the level vocabulary and threshold-filter contract for a2kit's LDD (logging / data / diagnostics) emissions. Locks the numeric ranks, the load-bearing invariant that the filter sits before every output channel, and the participation rules for `event()`, `report()`, `log()`, and the level shorthands. Lives separate from `runtime-config` because the filter mechanics (rank comparison, ambient-state plumbing) are independent of how the threshold value gets configured.
## Requirements
### Requirement: LDD emissions carry a level drawn from a fixed vocabulary

Every LDD emission SHALL carry a level value from the fixed set `{"trace", "debug", "info", "warning", "error"}`. The `log()` primitive's first positional argument SHALL be one of these values. The `event()` and `report()` primitives SHALL accept a keyword-only `level` parameter defaulting to `"info"`. The level shorthands SHALL bind: `debug() → "debug"`, `info() → "info"`, `warning() → "warning"`, `error() → "error"`. There is no `trace()` shorthand in this change; callers wanting trace use `log("trace", ...)`.

#### Scenario: log accepts trace level

- **WHEN** a tool calls `await log("trace", "fine-grained trace", k=1)`
- **THEN** the emission carries level `"trace"`

#### Scenario: event defaults to info

- **WHEN** a tool calls `await event("RowFetched", rows=10)`
- **THEN** the emission carries level `"info"`

#### Scenario: event accepts explicit level

- **WHEN** a tool calls `await event("RouterEntered", level="debug")`
- **THEN** the emission carries level `"debug"`

#### Scenario: report defaults to info

- **WHEN** a tool calls `await report(some_model)`
- **THEN** the emission carries level `"info"`

#### Scenario: shorthand primitives bind levels

- **WHEN** a tool calls `await debug("hello")`
- **THEN** the emission carries level `"debug"`
- **AND** when a tool calls `await warning("careful")` the emission carries level `"warning"`

### Requirement: LDD levels have numeric ranks for threshold comparison

Each level value SHALL map to a fixed numeric rank: `trace=10, debug=20, info=30, warning=40, error=50`. The mapping SHALL be exposed as an exported constant from the LDD package so sinks and tests can compare ranks deterministically without re-deriving them. Threshold comparison SHALL use these ranks (not string equality, not alphabetical order).

#### Scenario: rank mapping is fixed

- **WHEN** code reads `a2kit.packages.ldd.LDD_LEVEL_RANK`
- **THEN** the mapping is exactly `{"trace": 10, "debug": 20, "info": 30, "warning": 40, "error": 50}`

#### Scenario: ranks order levels low-to-high

- **WHEN** code compares `LDD_LEVEL_RANK["debug"] < LDD_LEVEL_RANK["info"]`
- **THEN** the result is `True`

### Requirement: Emissions below the configured threshold are dropped before any output channel

When an LDD primitive is called with a level whose rank is strictly less than the configured threshold rank, the primitive SHALL return immediately without calling `ctx.log(...)`, without calling `ctx._emit(...)`, and without dispatching to any sinks in `state.sinks`. The filter SHALL be the single volume control: no sink, no wire path, and no caller may observe a sub-threshold emission.

#### Scenario: debug emission dropped under info threshold

- **GIVEN** `A2KIT_LDD__LEVEL=info` (or default) and a tool body calling `await debug("noisy")`
- **WHEN** the tool runs
- **THEN** no sink receives an emission
- **AND** the MCP `ctx.log` is not called
- **AND** the CLI stderr does not show the line

#### Scenario: info emission passes under info threshold

- **GIVEN** `A2KIT_LDD__LEVEL=info` and a tool body calling `await info("notable")`
- **WHEN** the tool runs
- **THEN** sinks receive the emission
- **AND** the active transport's wire path is invoked

#### Scenario: trace threshold lets everything through

- **GIVEN** `A2KIT_LDD__LEVEL=trace`
- **WHEN** a tool calls `await log("trace", "deep")` and `await debug("verbose")` and `await info("notable")`
- **THEN** all three reach sinks

#### Scenario: error threshold drops everything below error

- **GIVEN** `A2KIT_LDD__LEVEL=error`
- **WHEN** a tool calls `await warning("almost")` followed by `await error("fail")`
- **THEN** sinks receive only the error emission

### Requirement: The threshold is read once per dispatch and stamped onto ambient state

The dispatch site (the LDD-state stage of `fold_pipeline`) SHALL obtain `LddConfig` via constructor injection at pipeline build time (or via a one-shot read of `spec.app.config.ldd` when the stage is built without explicit injection, e.g. the default module-level pipeline). The captured `LddConfig.level` SHALL be converted to its numeric rank via `LDD_LEVEL_RANK` once at wrap time and stamped onto the per-call ambient state object as `level_threshold: int`. Emission primitives SHALL read the threshold from the ambient state, not by re-resolving the App or its config on each call. The previous per-call attribute walk on `spec.app.config.ldd.level` is retired; `LddConfig` is treated as immutable for the lifetime of the runtime.

#### Scenario: Stage captures LddConfig at wrap time

- **GIVEN** a pipeline being constructed for an `App` whose `config.ldd.level` is `"warn"`
- **WHEN** `LddStateStage` wraps a tool
- **THEN** the captured `LddConfig.level` is `"warn"`
- **AND** the captured threshold is stamped onto every subsequent ambient state for that tool

#### Scenario: per-call state carries the threshold rank

- **WHEN** a tool dispatch is in progress with `app.config.ldd.level="debug"`
- **THEN** the ambient state's `level_threshold` is `20`

#### Scenario: Test rebinds LddConfig before build

- **GIVEN** a fresh `App` and a test that wants `LddConfig(level="debug")`
- **WHEN** the test calls `app.provide(LddConfig, lambda: LddConfig(level="debug"))` before building the runtime
- **THEN** the resulting pipeline's `LddStateStage` is constructed with the test-supplied `LddConfig`
- **AND** `ldd.debug(...)` emissions are not dropped

### Requirement: The events_enabled kill-switch is orthogonal to the threshold

The existing `events_enabled` boolean (driven by `A2KIT_LDD=off` / `--no-events`) SHALL continue to disable all LDD output regardless of level. When `events_enabled=False`, no emission reaches any sink even if its level rank meets or exceeds the threshold. When `events_enabled=True` (default), the threshold determines what passes.

#### Scenario: kill-switch off suppresses everything

- **GIVEN** `A2KIT_LDD=off` and `A2KIT_LDD__LEVEL=trace`
- **WHEN** a tool calls `await error("critical")`
- **THEN** no sink receives an emission

#### Scenario: kill-switch on, threshold filters

- **GIVEN** `A2KIT_LDD=on` (default) and `A2KIT_LDD__LEVEL=warning`
- **WHEN** a tool calls `await info("ignored")` and `await warning("noted")`
- **THEN** sinks receive only the warning emission


### Requirement: Emissions below the configured threshold are dropped before any output channel

When an LDD primitive is called with a level whose rank is strictly less than the configured threshold rank, the primitive SHALL return immediately without calling the wire sink (FastMCP `ctx.log`), without dispatching to any operator sink in `state.sinks`, and without spawning the fan-out task. The threshold filter is the single volume control, and it runs exactly ONCE per emission — before the operator/wire fan-out split.

#### Scenario: Sub-threshold emission reaches neither channel

- **GIVEN** `A2KIT_LDD__LEVEL=info` and a tool body calling `await debug("noisy")`
- **WHEN** the tool runs
- **THEN** no operator sink receives an emission
- **AND** the wire `ctx.log` is not called

#### Scenario: Above-threshold emission reaches both channels

- **GIVEN** `A2KIT_LDD__LEVEL=info`, a registered operator sink, and a connected MCP wire
- **WHEN** a tool body calls `await info("hello")`
- **THEN** both the operator sink and the wire sink receive the emission
