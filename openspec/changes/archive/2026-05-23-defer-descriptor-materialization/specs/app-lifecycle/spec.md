## ADDED Requirements

### Requirement: `AppRuntime` exposes canonical descriptor read surface

`AppRuntime` SHALL expose two read methods that are the canonical way for substrate adapters to obtain `ToolDescriptor` instances:

- `descriptor_for(name: str) -> ToolDescriptor` — O(1) lookup by tool name; raises `KeyError(name)` on miss.
- `descriptors() -> tuple[ToolDescriptor, ...]` — stable registration order, frozen tuple.

Substrate adapters (`packages/mcp/server.py`, `packages/http/build.py`, `packages/cli/builder.py`, `packages/codemode/marshal.py`) SHALL prefer these methods over `App.tools()` once the runtime is available, so they read descriptors whose container-dependent fields (`wire_param_names`, `lazy_param_names`) are populated.

#### Scenario: descriptor_for raises on unknown name

- **GIVEN** a built `AppRuntime` with no tool named `does_not_exist`
- **WHEN** `runtime.descriptor_for("does_not_exist")` is called
- **THEN** `KeyError("does_not_exist")` is raised

#### Scenario: descriptors() is a frozen tuple

- **GIVEN** a built `AppRuntime`
- **WHEN** `runtime.descriptors()` is called
- **THEN** the return value is a `tuple` in stable registration order
- **AND** the tuple's descriptors are the same objects returned by `descriptor_for(name)`
