## MODIFIED Requirements

### Requirement: Importable units are assigned ordered layers via a manifest

Every importable unit MUST be assigned an integer layer in a single declarative manifest hosted in `packages/lint/`. The units are:

- each directory under `src/a2kit/packages/`, and
- the top-level `a2kit.*` modules, split into three ordered sub-units rather than one `core` pseudo-unit: **`kernel`** (leaf type and helper modules that import no `a2kit` sibling — `exceptions`, `_context_protocol`, `metadata`, `_list_helpers`, `_lifecycle_helpers`, `_field_introspect`), **`authoring`** (the decoration-time surface — `_verbs`, `tool`, `signature`, `schema`, `routers`, `_verb_validators`), and **`runtime`** (`app`, `runtime`, `__main__`).

The re-export facade modules (`src/a2kit/__init__.py`, `src/a2kit/ldd.py`, `src/a2kit/testing.py`) are a layer-exempt group: they exist to surface deeper layers as a flat public API and are not layered units. The manifest MUST cover every unit — none may be unassigned. `unit_for_module` and `unit_for_path` SHALL map each top-level module to its specific sub-unit.

#### Scenario: every unit has a layer

- **WHEN** the layer manifest is checked against the directories under `src/a2kit/packages/` plus the three core sub-units (`kernel`, `authoring`, `runtime`)
- **THEN** every unit has exactly one layer assignment

#### Scenario: core sub-units are ordered kernel below authoring below runtime

- **WHEN** the manifest is read
- **THEN** `kernel` has a layer strictly below `authoring`, and `authoring` has a layer strictly below `runtime`

#### Scenario: authoring sits above the kernel packages and below the transports

- **WHEN** the manifest is read
- **THEN** `authoring` has a layer strictly above the kernel packages (`di`, `formatter`, `ldd`, `health`, `lint`) and strictly below the transport packages (`cli`, `mcp`, `codemode`, `otel`)

### Requirement: Imports respect layer order

A unit MUST NOT import a unit assigned a higher layer. A same-layer import MUST NOT close an import cycle. The `A2K-LAYER` lint rule enforces this for core-to-package, package-to-core, package-to-package, and intra-core sub-unit edges (`kernel`, `authoring`, `runtime`), and MUST account for `TYPE_CHECKING`-guarded imports.

The facade group is exempt: a facade module MAY import any layer, because it exists solely to re-export deeper layers as a flat public surface.

#### Scenario: higher-layer import is flagged

- **WHEN** a kernel-layer package imports a transport-layer package
- **THEN** `a2kit lint static` reports `A2K-LAYER` against that import

#### Scenario: authoring importing a kernel package is clean

- **WHEN** a module in the `authoring` sub-unit imports a kernel-layer package
- **THEN** `A2K-LAYER` does not fire (authoring is above the kernel)

#### Scenario: intra-core upward edge is flagged

- **WHEN** a `kernel` sub-unit module imports `a2kit.app` (a `runtime` sub-unit module), or an `authoring` module imports a `runtime` module
- **THEN** `a2kit lint static` reports `A2K-LAYER` against that import

#### Scenario: a type-only cycle is flagged

- **WHEN** two units import each other and at least one import is guarded by `TYPE_CHECKING`
- **THEN** `a2kit lint static` reports `A2K-LAYER`

#### Scenario: a facade module importing upward is clean

- **WHEN** `src/a2kit/__init__.py` imports from `a2kit.app` or `a2kit.packages.cli`
- **THEN** `A2K-LAYER` does not fire, because facade modules are layer-exempt

### Requirement: Core modules are organized by sub-unit

Every top-level Python module in `src/a2kit/` SHALL be assigned to exactly one core sub-unit — `kernel`, `authoring`, or `runtime` — in the layer manifest, or be one of the layer-exempt re-export facades (`__init__.py`, `ldd.py`, `testing.py`).

The structural control on core growth is this sub-unit layering, not a flat file-count cap. A new top-level module is acceptable when it has a clear sub-unit home and introduces no upward or cyclic import edge. The earlier "at most 12 core files" cap is retired: it predates the layer manifest, the tree already exceeded it, and a flat count says nothing about whether a module sits in the right layer. The `A2K-LAYER`-enforced sub-unit manifest is the organizing principle.

The core LOC budget is unaffected: top-level `src/a2kit/` source remains bounded by the separate LOC requirement.

#### Scenario: every top-level module has a sub-unit home

- **WHEN** the layer manifest is checked against the top-level `.py` files in `src/a2kit/`
- **THEN** each module is assigned to `kernel`, `authoring`, or `runtime`, or is a layer-exempt facade
- **AND** no top-level module is unaccounted for
