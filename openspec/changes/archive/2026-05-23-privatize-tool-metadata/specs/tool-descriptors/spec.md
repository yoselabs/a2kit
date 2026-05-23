## ADDED Requirements

### Requirement: `ToolDescriptor` is the sole external read surface for tool meta

External code (anything outside `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`) SHALL read tool metadata via `AppRuntime.descriptor_for(name)` only. Direct access to `A2KitMeta` via `metadata._get_meta` from substrate adapters, packages, or downstream consumers is forbidden and enforced by lint rule `A2K-METADATA-PRIVATE`.

The public `metadata.get_meta` / `metadata.set_meta` names SHALL remain as migration-hint raises (`AttributeError` pointing to `ToolDescriptor`); they SHALL NOT return meta.

#### Scenario: substrate adapter reads via descriptor

- **GIVEN** a substrate adapter needs the tool's `annotations` dict
- **WHEN** it accesses the data
- **THEN** it reads `runtime.descriptor_for(name).annotations_view`
- **AND** it does NOT import `_get_meta` from `a2kit.metadata`

#### Scenario: legacy public name raises migration hint

- **WHEN** code calls `from a2kit.metadata import get_meta; get_meta(fn)`
- **THEN** `AttributeError` is raised
- **AND** the message names `ToolDescriptor` and `runtime.descriptor_for` as the replacement
