## ADDED Requirements

### Requirement: Importable units are assigned ordered layers via a manifest

Every importable unit MUST be assigned an integer layer in a single
declarative manifest hosted in `packages/lint/`. The units are each
directory under `src/a2kit/packages/` and one `core` pseudo-unit
covering the top-level `a2kit.*` modules. The manifest MUST cover every
unit — none may be unassigned.

#### Scenario: every unit has a layer

- **WHEN** the layer manifest is checked against the directories under
  `src/a2kit/packages/` plus the `core` pseudo-unit
- **THEN** every unit has exactly one layer assignment

#### Scenario: core sits between kernel and consumers

- **WHEN** the manifest is read
- **THEN** `core` has a layer strictly above the kernel packages
  (`di`, `formatter`, `ldd`, `health`, `select`, `lint`) and strictly
  below the transport packages (`cli`, `mcp`, `codemode`, `otel`)

### Requirement: Imports respect layer order

A unit MUST NOT import a unit assigned a higher layer. A same-layer
import MUST NOT close an import cycle. The `A2K-LAYER` lint rule
enforces this for core-to-package, package-to-core, and
package-to-package edges, and MUST account for `TYPE_CHECKING`-guarded
imports.

#### Scenario: higher-layer import is flagged

- **WHEN** a kernel-layer package imports a transport-layer package
- **THEN** `a2kit lint static` reports `A2K-LAYER` against that import

#### Scenario: core importing a kernel package is clean

- **WHEN** `app.py` imports a kernel-layer package
- **THEN** `A2K-LAYER` does not fire (core is above the kernel)

#### Scenario: a kernel package importing core is flagged

- **WHEN** a kernel-layer package imports `a2kit.app`
- **THEN** `a2kit lint static` reports `A2K-LAYER` (an upward edge)

#### Scenario: a type-only cycle is flagged

- **WHEN** two units import each other and at least one import is
  guarded by `TYPE_CHECKING`
- **THEN** `a2kit lint static` reports `A2K-LAYER`

### Requirement: Cross-package imports target the package front door

Code outside package `X` MUST NOT import
`a2kit.packages.X.<submodule>`; it MUST import from
`a2kit.packages.X` (the package `__init__`). The `A2K-PKG-FRONT-DOOR`
lint rule enforces this, with a documented allowlist for deliberate
exceptions.

#### Scenario: deep cross-package import is flagged

- **WHEN** `app.py` imports `a2kit.packages.di.container`
- **THEN** `a2kit lint static` reports `A2K-PKG-FRONT-DOOR`

#### Scenario: front-door import is clean

- **WHEN** `app.py` imports `Container` from `a2kit.packages.di`
- **THEN** `A2K-PKG-FRONT-DOOR` does not fire

#### Scenario: same-package submodule import is clean

- **WHEN** a module inside package `di` imports a sibling `di`
  submodule directly
- **THEN** `A2K-PKG-FRONT-DOOR` does not fire

#### Scenario: allowlisted deep import is clean

- **WHEN** an import path is listed in the `A2K-PKG-FRONT-DOOR`
  allowlist
- **THEN** the rule does not fire for that import

## MODIFIED Requirements

### Requirement: `__init__.py` files are minimized to package boundaries

The package SHALL contain only the `__init__.py` files required by real
package boundaries: one for the core (`src/a2kit/__init__.py`), one for
the packages namespace (`src/a2kit/packages/__init__.py`), one per
plugin package under `src/a2kit/packages/<name>/__init__.py`, and one
for the `packages/lint/rules/` subpackage that hosts the split rule
modules.

The `__init__.py` count SHALL equal `2 + N + R` where:

- `N` is the count of plugin packages under `src/a2kit/packages/`
- `R` is the count of rule subpackages under plugin packages (currently
  one: `packages/lint/rules/`)

Public re-exports in a package `__init__.py` (the package's declared
front door, per the `A2K-PKG-FRONT-DOOR` rule) are part of the package
boundary and do not violate this requirement.

#### Scenario: __init__.py count tracks the formula

- **WHEN** `find src/a2kit -type f -name "__init__.py" | wc -l` is run
- **THEN** the result equals `2 + N + R`, where `N` is the actual count
  of plugin packages under `src/a2kit/packages/` (including `context`)
  and `R` is `1`

#### Scenario: No additional core subpackages

- **WHEN** `find src/a2kit -maxdepth 1 -type d -not -name "__pycache__"`
  is run
- **THEN** the result is `src/a2kit` and `src/a2kit/packages` only — no
  other core subpackages
