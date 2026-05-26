## MODIFIED Requirements

### Requirement: Emissions below the configured threshold are dropped before any output channel

When an LDD primitive is called with a level whose rank is strictly less than the configured threshold rank, the primitive SHALL return immediately without calling the wire sink (FastMCP `ctx.log`), without dispatching to any operator sink in `state.sinks`, and without spawning the fan-out task. The threshold filter is the single volume control, and it runs exactly ONCE per emission — before the operator/wire fan-out split. No sink, no wire path, and no caller may observe a sub-threshold emission.

Adds clarification (no behaviour change vs the existing requirement): the fan-out introduced by `ldd-operator-sinks` runs only after the threshold accepts the emission.

#### Scenario: Sub-threshold emission reaches neither channel

- **GIVEN** `A2KIT_LDD__LEVEL=info` and a tool body calling `await debug("noisy")`
- **WHEN** the tool runs
- **THEN** no operator sink receives an emission
- **AND** the wire `ctx.log` is not called
- **AND** the fan-out task is not spawned

#### Scenario: Above-threshold emission reaches both channels

- **GIVEN** `A2KIT_LDD__LEVEL=info`, a registered operator sink, and a connected MCP wire
- **WHEN** a tool body calls `await info("hello")`
- **THEN** both the operator sink and the wire sink receive the emission
- **AND** the threshold check runs only once
