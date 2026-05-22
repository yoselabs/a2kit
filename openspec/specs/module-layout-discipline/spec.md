# module-layout-discipline Specification

## Purpose
TBD - created by archiving change simplify-and-thin-core. Update Purpose after archive.
## Requirements
### Requirement: No underscore-prefixed modules with public symbols

A Python file in `src/a2kit/` SHALL NOT use a leading-underscore filename (e.g. `_foo.py`) while exporting symbols that are referenced from outside its parent package. Each file is either inlined into its parent module or promoted to a public, non-underscore name.

#### Scenario: Source tree contains zero underscore-prefixed modules
- **WHEN** `find src/a2kit -type f -name "_*.py" -not -name "__init__.py"` is run after the change
- **THEN** the result is empty

#### Scenario: Public symbols live in public files
- **WHEN** a symbol is imported from `a2kit` or `a2kit.<subpackage>` by external code
- **THEN** the source file defining that symbol does not start with an underscore

### Requirement: One concept per file, name equals concept

Every file in `src/a2kit/` SHALL answer "what is this?" by its filename alone, without requiring a docstring or comment to explain the file's existence.

#### Scenario: File names are self-evident
- **WHEN** a reader scans `ls src/a2kit/` and `ls src/a2kit/<subpackage>/`
- **THEN** every filename maps to a single, namable concept (e.g. `connections.py`, `decorator.py`, `enrichers.py`) — not a slice of one (e.g. `_decorator_impl.py`, `_decorator_helpers.py`)

#### Scenario: No "helper" or "utils" modules
- **WHEN** the source tree is inspected after the change
- **THEN** no module is named `helpers.py`, `utils.py`, `common.py`, `_helpers.py`, `_utils.py`, or `_common.py`

### Requirement: `__init__.py` files are minimized to package boundaries

The package SHALL contain only the `__init__.py` files required by real
package boundaries: one for the core (`src/a2kit/__init__.py`), one for
the packages namespace (`src/a2kit/packages/__init__.py`), one per plugin
package under `src/a2kit/packages/<name>/__init__.py`, and one for the
`packages/lint/rules/` subpackage that hosts the split rule modules.

The `__init__.py` count SHALL equal `2 + N + R` where:
- `N` is the count of plugin packages under `src/a2kit/packages/`
- `R` is the count of rule subpackages under plugin packages (currently
  one: `packages/lint/rules/`)

#### Scenario: __init__.py count tracks the formula
- **WHEN** `find src/a2kit -type f -name "__init__.py" | wc -l` is run
- **THEN** the result equals `2 + N + R` (target after this change:
  `2 + 9 + 1 = 12`, where N=9 plugins now includes `otel`)

#### Scenario: No additional core subpackages
- **WHEN** `find src/a2kit -maxdepth 1 -type d -not -name "__pycache__"` is run
- **THEN** the result is `src/a2kit` and `src/a2kit/packages` only — no
  other core subpackages

### Requirement: Core source tree is at most 12 files

Core source SHALL contain at most 12 Python files at the top level of `src/a2kit/` (excluding `__init__.py`, `__main__.py`, and the `packages/` subtree).

#### Scenario: Core file count under threshold
- **WHEN** `find src/a2kit -maxdepth 1 -type f -name "*.py" -not -name "__init__.py" -not -name "__main__.py" | wc -l` is run
- **THEN** the result is ≤ 12

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

### Requirement: `_APP_CTX` lives in `packages/cli/app_ctx`

`_APP_CTX: ContextVar` SHALL be defined exactly once, in `a2kit.packages.cli.app_ctx`, and SHALL be used by `build_full_cli` and `serve_command` to propagate the active `App` across lazy subcommand dispatches. The previous Phase-3.1 location (`a2kit.packages.mcp.cli._APP_CTX`) is replaced; no compatibility re-export.

#### Scenario: Canonical location
- **WHEN** the source tree is inspected
- **THEN** `_APP_CTX` is defined exactly once, in
  `src/a2kit/packages/cli/app_ctx.py`

#### Scenario: mcp.cli imports from cli.app_ctx
- **WHEN** `src/a2kit/packages/mcp/cli.py` is read
- **THEN** it imports `_APP_CTX` from `a2kit.packages.cli.app_ctx`, not
  the reverse

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

The A2K010 rule and all its supporting code paths SHALL be removed from
`a2kit.packages.lint`. The rule code and its disable list entries SHALL
not appear in `pyproject.toml [tool.a2kit.lint]`.

#### Scenario: A2K010 not in ALL_RULES
- **WHEN** `a2kit.packages.lint.ALL_RULES` is inspected
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

