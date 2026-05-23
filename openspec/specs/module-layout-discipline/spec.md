# module-layout-discipline Specification

## Purpose
TBD - created by archiving change simplify-and-thin-core. Update Purpose after archive.
## Requirements
### Requirement: One concept per file, name equals concept

Every file in `src/a2kit/` SHALL answer "what is this?" by its filename alone, without requiring a docstring or comment to explain the file's existence. Filenames SHALL name a single concept rather than a slice of one.

#### Scenario: File names are self-evident

- **WHEN** a reader scans `ls src/a2kit/` and `ls src/a2kit/<subpackage>/`
- **THEN** every filename maps to a single, namable concept (e.g. `tool.py`, `routers.py`, `app.py`) — not a slice of one (e.g. `_decorator_impl.py`, `_decorator_helpers.py`)

#### Scenario: No "helper" or "utils" modules

- **WHEN** the source tree is inspected
- **THEN** no module is named `helpers.py`, `utils.py`, `common.py`, `_utils.py`, or `_common.py` (the allowlisted `_lifecycle_helpers.py` and `_list_helpers.py` are named for their concept — verb-lifecycle and list-verb decoration — not as generic "helpers" buckets)

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

### Requirement: Core modules are organized by sub-unit

Every top-level Python module in `src/a2kit/` SHALL be assigned to exactly one core sub-unit — `kernel`, `authoring`, or `runtime` — in the layer manifest, or be one of the layer-exempt re-export facades (`__init__.py`, `ldd.py`, `testing.py`).

The structural control on core growth is this sub-unit layering, not a flat file-count cap. A new top-level module is acceptable when it has a clear sub-unit home and introduces no upward or cyclic import edge. The earlier "at most 12 core files" cap is retired: it predates the layer manifest, the tree already exceeded it, and a flat count says nothing about whether a module sits in the right layer. The `A2K-LAYER`-enforced sub-unit manifest is the organizing principle.

The core LOC budget is unaffected: top-level `src/a2kit/` source remains bounded by the separate LOC requirement.

#### Scenario: every top-level module has a sub-unit home

- **WHEN** the layer manifest is checked against the top-level `.py` files in `src/a2kit/`
- **THEN** each module is assigned to `kernel`, `authoring`, or `runtime`, or is a layer-exempt facade
- **AND** no top-level module is unaccounted for

### Requirement: Core source LOC is at most 2000

The total line count of Python source at the top level of `src/a2kit/` (excluding the `packages/` subtree) SHALL be at most 2000 lines. The `packages/` subtree is excluded from this budget.

#### Scenario: Core LOC under threshold
- **WHEN** `find src/a2kit -maxdepth 1 -type f -name "*.py" | xargs wc -l | tail -1` is run after the change
- **THEN** the total is ≤ 2000

### Requirement: Test directory mirrors source structure

The `tests/` directory SHALL mirror the structure of `src/a2kit/`. Top-level a2kit modules have corresponding `tests/test_<module>.py`. Plugin packages have corresponding `tests/packages/<name>/test_*.py` subdirectories matching the file structure of `src/a2kit/packages/<name>/`.

#### Scenario: Tests slice cleanly by package
- **WHEN** a developer runs `pytest tests/packages/connections/` after the change
- **THEN** the result exercises only the `packages/connections/` code paths

#### Scenario: Top-level modules have flat tests
- **WHEN** a top-level module like `tool.py` exists in `src/a2kit/`
- **THEN** a corresponding `tests/test_tool.py` exists

#### Scenario: Subpackage tests live under packages/
- **WHEN** a plugin package like `mcp/server.py` exists at `src/a2kit/packages/mcp/server.py`
- **THEN** a corresponding `tests/packages/mcp/test_server.py` exists

### Requirement: No comments explaining what code does

Source comments SHALL only document non-obvious **why** (hidden constraints, invariants, workarounds for specific bugs). Comments that paraphrase the code, describe what the function does, or summarize the file's contents SHALL be removed.

#### Scenario: Module-level docstrings are absent or single-line
- **WHEN** a module is inspected after the change
- **THEN** any module-level docstring is at most one line, or absent if the filename + symbol names are self-evident

#### Scenario: Function bodies are uncommented unless preserving non-obvious why
- **WHEN** a function body is inspected
- **THEN** comments inside it document only non-obvious constraints, not the code's behavior

### Requirement: Lint rules split into per-family modules

`a2kit.packages.lint.static` SHALL be split into a slim dispatch entry
(`static.py`, ≤ 250 SLOC) plus a `rules/` subpackage containing one module
per rule family. `static.py` SHALL only define `LintMessage`,
`run_static`, the dispatch table, and shared helpers; rule logic lives in
`rules/`.

#### Scenario: static.py size budget
- **WHEN** `wc -l src/a2kit/packages/lint/static.py` is run after the change
- **THEN** the result is ≤ 250

#### Scenario: rules/ subpackage exists
- **WHEN** `ls src/a2kit/packages/lint/rules/` is run
- **THEN** the listing contains at least: `__init__.py`, `di.py`, `conn.py`,
  `importing.py`, `shape.py`, `budget.py`

#### Scenario: A2K014 stops firing on the lint package itself
- **WHEN** `uv run a2kit lint static src/a2kit/` is run after the change
- **THEN** no A2K014 finding targets `src/a2kit/packages/lint/static.py`

### Requirement: A2K010 (legacy `--select` atom rule) is retired

The A2K010 rule and all its supporting code paths SHALL be removed from `a2kit.packages.lint`. The rule code and its disable list entries SHALL not appear in `pyproject.toml [tool.a2kit.lint]`.

#### Scenario: A2K010 not in ALL_RULES
- **WHEN** `a2kit.packages.lint.static.ALL_RULES` is inspected
- **THEN** the tuple does not contain `"A2K010"`

#### Scenario: No `_parse_select_atoms_cel` stub
- **WHEN** `grep -rE "_parse_select_atoms_cel|A2K010" src/a2kit/packages/lint/` is run
- **THEN** the result is empty

### Requirement: Test layout uniformity for stdlib-name collisions

`tests/packages/<name>/` directories SHALL all contain an `__init__.py`,
including `tests/packages/select/`. Where the package name shadows a
stdlib module (e.g. `select`), `pyproject.toml` SHALL declare
`[tool.pytest.ini_options] importmode = "importlib"` so pytest loads
test modules by file path, avoiding the `sys.modules` collision.

#### Scenario: All test package dirs have __init__.py
- **WHEN** `find tests/packages -mindepth 1 -maxdepth 1 -type d -not -exec test -e {}/__init__.py \; -print` is run
- **THEN** the result is empty

#### Scenario: importlib mode in pyproject
- **WHEN** `pyproject.toml [tool.pytest.ini_options]` is inspected
- **THEN** `importmode = "importlib"` is set

### Requirement: DI factory-introspection helpers SHALL live in their own module

DI factory-introspection helpers (`Factory`, `UnresolvableType`, `_ParamSpec`, `_factory_callable`, `_factory_params`, `_is_primitive_or_external`) SHALL live in `src/a2kit/packages/di/_introspection.py` so `container.py` stays under the A2K014 SLOC budget without suppression.

#### Scenario: Introspection helpers importable from the sibling module

- **WHEN** consumer code or tests do `from a2kit.packages.di._introspection import _factory_params`
- **THEN** the import succeeds and the symbol resolves to the parameter-introspection function

#### Scenario: container.py stays under SLOC budget without suppression

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/packages/di/container.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

### Requirement: list-verb decoration helpers SHALL live in their own module

The list-verb decoration-time validators SHALL live in `src/a2kit/_list_helpers.py`, exporting `check_list_return_annotation` and `derive_selectable_fields`. The verb decorators themselves (`read`, `write`, `list_`) SHALL be re-exported from `a2kit.tool` but their decoration-time bodies SHALL live in `src/a2kit/_verbs.py`. `tool.py` SHALL NOT carry a `# noqa: A2K014` suppression after the verb extraction lands.

#### Scenario: List helpers importable from the sibling module

- **WHEN** consumer code or tests do `from a2kit._list_helpers import derive_selectable_fields`
- **THEN** the import succeeds and the symbol resolves to the fields-derivation function

#### Scenario: Verb decorators importable from `a2kit.tool`

- **WHEN** consumer code imports `from a2kit.tool import read, write, list_`
- **THEN** the imports succeed and the decorators behave identically to pre-extraction

#### Scenario: Verb decoration bodies live in `_verbs.py`

- **WHEN** `from a2kit._verbs import read, write, list_` is executed
- **THEN** the import succeeds and `a2kit.tool.read is a2kit._verbs.read` (same object, re-exported)

#### Scenario: tool.py is noqa-free under the A2K014 budget

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/tool.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

### Requirement: Mirror-rule ALLOW_LIST SHALL permit `_verbs.py`

`src/a2kit/packages/lint/rules/mirror.py` SHALL list `_verbs.py` in its ALLOW_LIST of private sibling modules permitted to coexist with their public counterparts, alongside `_lifecycle_helpers.py`, `_list_helpers.py`, and `packages/di/_introspection.py`.

#### Scenario: Mirror rule allows `_verbs.py`

- **WHEN** `uv run a2kit lint static src/` runs against the source tree containing `src/a2kit/_verbs.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verbs.py`

### Requirement: Verb-decorator validators SHALL live in their own module

The return-annotation validators and reserved-name guards used by `@a2kit.read` / `@write` / `@list_` SHALL live in `src/a2kit/_verb_validators.py`, exporting `_check_return`, `_resolve_return_annotation`, `_check_reserved_name`, `_BUILTIN_RESERVED_TOOL_NAMES`, and `_RESERVED_TOOL_NAME_PREFIX`. `_verbs.py` SHALL re-export `_resolve_return_annotation` and the `_WARN_ONCE_RESOLVE_RETURN` set for test access.

#### Scenario: Validators importable from the sibling module

- **WHEN** consumer code does `from a2kit._verb_validators import _check_return, _resolve_return_annotation`
- **THEN** the imports succeed and the symbols resolve to the introspection functions

#### Scenario: `_verbs.py` stays under the SLOC budget

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/_verbs.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

#### Scenario: Mirror rule allows `_verb_validators.py`

- **WHEN** `uv run a2kit lint static src/` runs against the source tree containing `src/a2kit/_verb_validators.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verb_validators.py`

### Requirement: Submodules do not import from their own package `__init__`

A Python file under `src/a2kit/` that is not itself a package `__init__.py` SHALL NOT import from its own package's `__init__.py`, in either the absolute form (`from a2kit.<...>.<package> import ...`) or the relative form (`from . import ...`). Symbols shared between a package's `__init__.py` and its submodules SHALL live in a dedicated leaf module that both import from. This rule forbids the latent import cycle in which a package `__init__` aggregates a public surface that its own submodules then need. A static lint rule SHALL enforce it and surface findings under `a2kit lint static`.

#### Scenario: Submodule importing its own package `__init__` is flagged
- **WHEN** `a2kit lint static src/` runs against a file `src/a2kit/packages/<pkg>/<sub>.py` that contains `from a2kit.packages.<pkg> import X` or `from . import X`
- **THEN** a lint finding is emitted naming the offending import

#### Scenario: Importing from a sibling submodule is allowed
- **WHEN** `a2kit lint static src/` runs against a submodule that imports from a sibling module (e.g. `from .formats import FormatName`) or from any other package
- **THEN** no such finding is emitted

#### Scenario: A package `__init__` may import its own submodules
- **WHEN** the rule runs against a package's own `__init__.py` that re-exports symbols from its submodules
- **THEN** no finding is emitted, because the aggregation direction is `__init__` importing submodule, never the reverse

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

### Requirement: Underscore-prefixed modules are confined to an allowlisted set of private siblings

A Python file in `src/a2kit/` with a leading-underscore filename (e.g. `_foo.py`) SHALL exist only as an allowlisted private sibling of a public module — a deliberate code-split that keeps the public file under the SLOC budget. The allowlist is enforced by `src/a2kit/packages/lint/rules/mirror.py` and currently includes `_lifecycle_helpers.py`, `_list_helpers.py`, `_verbs.py`, `_verb_validators.py`, and `packages/di/_introspection.py`. An underscore-prefixed module that is NOT on this allowlist SHALL be flagged by the mirror lint rule. Symbols re-exported from a private sibling SHALL be re-exported through its public counterpart so external code imports the public name.

This requirement supersedes the earlier blanket prohibition on underscore-prefixed modules: that prohibition contradicted later requirements in this same capability that REQUIRE `_verbs.py` and `_verb_validators.py` to exist. The reconciled rule is "underscore modules are allowed only as allowlisted private siblings," which the code's mirror rule already enforces.

#### Scenario: Allowlisted private sibling is permitted

- **WHEN** `uv run a2kit lint static src/` runs against a tree containing `src/a2kit/_verbs.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verbs.py` (it is on the ALLOW_LIST)

#### Scenario: Non-allowlisted underscore module is flagged

- **WHEN** `uv run a2kit lint static src/` runs against a tree containing a new `src/a2kit/_scratch.py` not on the ALLOW_LIST
- **THEN** the mirror lint rule reports `_scratch.py`

#### Scenario: Public symbols are re-exported through public files

- **WHEN** external code imports a verb decorator
- **THEN** it imports `from a2kit.tool import read` (a public module), even though the decoration body lives in the private sibling `_verbs.py`

### Requirement: A package `__init__.py` is a re-export front door, not an implementation site

A plugin-package `__init__.py` under `src/a2kit/packages/<name>/` SHALL contain only front-door plumbing: imports, re-exports, module-level constants, an `__all__`, and an optional lazy re-export `__getattr__` / `__dir__` pair for cold-start deferral. It SHALL NOT define implementation — a top-level `class` or a top-level `def` / `async def` other than the lazy `__getattr__` / `__dir__` pair. Implementation SHALL live in named submodules of the package. A static lint rule (`A2K-PKG-INIT-IMPL`) SHALL enforce this and surface findings under `a2kit lint static`.

The `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, and `testing` packages SHALL be brought into compliance: their `__init__.py` implementation moves into named submodules and their `__init__.py` is reduced to re-exports. With every package compliant, the rule SHALL report zero findings against `src/a2kit/`.

#### Scenario: Implementation in `__init__.py` is flagged

- **WHEN** `a2kit lint static src/` runs against a package `__init__.py` that defines a class body or a logic-bearing function
- **THEN** a lint finding is emitted naming the offending definition

#### Scenario: Re-export front door is clean

- **WHEN** `a2kit lint static src/` runs against a package `__init__.py` that only imports, re-exports, declares `__all__`, and optionally defines a lazy re-export `__getattr__` / `__dir__`
- **THEN** no such finding is emitted

#### Scenario: Every init-heavy package has a re-export-only front door

- **WHEN** the `__init__.py` of `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, and `testing` are inspected after the change
- **THEN** each contains only re-export front-door plumbing
- **AND** the package's implementation lives in named submodules alongside it

#### Scenario: The rule reports clean against the whole source tree

- **WHEN** `a2kit lint static src/` runs after the splits land
- **THEN** the `A2K-PKG-INIT-IMPL` rule emits no findings

#### Scenario: Root-level imports are unaffected

- **WHEN** existing consumer code imports a symbol from one of the seven packages' roots (`a2kit.packages.<name>`)
- **THEN** the import resolves exactly as before the split


### Requirement: `A2K-METADATA-PRIVATE` lint rule

A lint rule `A2K-METADATA-PRIVATE` SHALL AST-scan every file under `src/a2kit/` and reject any import of `_get_meta` or `_set_meta` from `a2kit.metadata` unless the importing module is in the allowlist `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`.

The allowlist SHALL be a frozen constant at the top of the rule module (`packages/lint/rules/metadata_private.py`). Test files under `tests/` are exempt via the standard `is_fixture_path` filter — tests inspecting decorator-time stamping pre-`build()` may import `_get_meta` directly.

#### Scenario: substrate adapter importing `_get_meta` is rejected

- **GIVEN** a file `src/a2kit/packages/mcp/server.py` contains `from a2kit.metadata import _get_meta`
- **WHEN** `make lint` runs
- **THEN** `A2K-METADATA-PRIVATE` raises naming the offending file
- **AND** the message points to `runtime.descriptor_for(name)` as the replacement

#### Scenario: allowlisted module passes

- **GIVEN** `src/a2kit/app.py` imports `_get_meta` from `a2kit.metadata`
- **WHEN** `make lint` runs
- **THEN** `A2K-METADATA-PRIVATE` does not flag it
