# component-map Specification

## Purpose
TBD - created by archiving change component-map. Update Purpose after archive.
## Requirements
### Requirement: The component map is auto-generated from the layer manifest

A generator script at `scripts/component_map.py` SHALL produce `docs/COMPONENT_MAP.md` by reading the layer manifest in `packages/lint/layers.py` and the parsed import graph of `src/a2kit/`. The generator SHALL NOT maintain a second copy of the unit-to-layer assignment — it SHALL import that assignment from the manifest module. A `make component-map` target SHALL run the generator.

#### Scenario: Generator reads the manifest, not a copy

- **WHEN** `scripts/component_map.py` is inspected
- **THEN** it imports unit-and-layer assignment from `a2kit.packages.lint.layers`
- **AND** it does not redefine the layer manifest

#### Scenario: make target regenerates the map

- **WHEN** `make component-map` is run
- **THEN** `docs/COMPONENT_MAP.md` is written with the current component graph

### Requirement: The component map covers every layer-manifest unit

`docs/COMPONENT_MAP.md` SHALL list every unit present in the layer manifest, each with its layer, its dependency edges, and its fan-in and fan-out counts. The document SHALL render the units in layer order so the DAG is readable top-to-bottom.

#### Scenario: Every manifest unit appears

- **WHEN** `docs/COMPONENT_MAP.md` is compared against the layer manifest
- **THEN** every unit in the manifest appears in the document exactly once

#### Scenario: Document is agent-loadable markdown

- **WHEN** `docs/COMPONENT_MAP.md` is opened
- **THEN** it is a single markdown file readable in one pass, with a unit table and a layer-ordered DAG rendering

### Requirement: A pre-commit staleness gate keeps the map current

A pre-commit hook SHALL regenerate the component map and fail the commit if the committed `docs/COMPONENT_MAP.md` differs from the freshly generated output. This mirrors the existing `adr-index` staleness gate.

#### Scenario: Stale map blocks the commit

- **WHEN** a change alters the import graph but `docs/COMPONENT_MAP.md` is not regenerated
- **THEN** the pre-commit hook regenerates the map, detects the difference, and fails the commit

#### Scenario: Current map passes

- **WHEN** `docs/COMPONENT_MAP.md` already matches the generator output
- **THEN** the pre-commit hook passes

