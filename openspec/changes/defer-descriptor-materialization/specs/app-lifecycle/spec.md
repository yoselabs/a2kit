## ADDED Requirements

### Requirement: `AppRuntime` exposes canonical descriptor read surface

`AppRuntime` SHALL expose two read methods that are the canonical way for substrate adapters to obtain `ToolDescriptor` instances:

- `descriptor_for(name: str) -> ToolDescriptor` — O(1) lookup by tool name; raises `KeyError(name)` on miss.
- `descriptors() -> tuple[ToolDescriptor, ...]` — stable registration order, frozen tuple.

Substrate adapters (`packages/mcp/server.py`, `packages/http/build.py`, `packages/cli/builder.py`, `packages/codemode/marshal.py`) SHALL consume descriptors via these methods only. Re-deriving wire shape via `wire_input_params(fn, container)` at the substrate layer is forbidden once this change lands.

#### Scenario: substrate reads descriptor instead of re-deriving

- **GIVEN** a built `AppRuntime` with tool `fetch(*, db: Database, id: str)`
- **WHEN** the MCP server prepares the wire schema for `fetch`
- **THEN** it reads `runtime.descriptor_for("fetch").wire_param_names`
- **AND** does NOT call `wire_input_params(fn, container)` directly

#### Scenario: descriptor_for raises on unknown name

- **GIVEN** a built `AppRuntime` with no tool named `does_not_exist`
- **WHEN** `runtime.descriptor_for("does_not_exist")` is called
- **THEN** `KeyError("does_not_exist")` is raised
