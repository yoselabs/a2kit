## ADDED Requirements

### Requirement: `_APP_CTX` lives in `packages/cli/app_ctx`

The shared `_APP_CTX: ContextVar` used by `build_full_cli` and
`serve_command` to propagate the active `App` across lazy subcommand
dispatches SHALL be defined in `a2kit.packages.cli.app_ctx`. Both adapters
import from there. The previous Phase-3.1 location
(`a2kit.packages.mcp.cli._APP_CTX`) is replaced; no compatibility re-export.

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

## MODIFIED Requirements

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

The total count of Python source files at the top level of `src/a2kit/`
(`src/a2kit/*.py`, excluding `__init__.py` and `__main__.py`, and
excluding the `packages/` subtree) SHALL be at most 12.

#### Scenario: Core file count under threshold
- **WHEN** `find src/a2kit -maxdepth 1 -type f -name "*.py" -not -name "__init__.py" -not -name "__main__.py" | wc -l` is run
- **THEN** the result is ≤ 12
