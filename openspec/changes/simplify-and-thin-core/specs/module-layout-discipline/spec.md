## ADDED Requirements

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

The package SHALL contain only the `__init__.py` files required by real package boundaries: one for the core (`src/a2kit/__init__.py`), one for the packages namespace (`src/a2kit/packages/__init__.py`), and one per plugin package under `src/a2kit/packages/<name>/__init__.py`. No subpackages are permitted at the top level (no `tools/`, `middleware/`, `scaffold/`, `contrib/`, or `lint/` subpackages in core).

#### Scenario: __init__.py count matches package boundaries
- **WHEN** `find src/a2kit -type f -name "__init__.py" | wc -l` is run after the change
- **THEN** the result equals `2 + N` where `N` is the count of plugin packages under `src/a2kit/packages/` (target: 9 total = core + packages namespace + 7 plugins)

#### Scenario: No core subpackages
- **WHEN** `find src/a2kit -maxdepth 1 -type d | wc -l` is run after the change
- **THEN** the result is `2` (the `a2kit` directory itself and `packages/`); no other subdirectories exist at the top level

#### Scenario: No subpackage re-exports of private modules
- **WHEN** any `__init__.py` is inspected
- **THEN** it does NOT import symbols from underscore-prefixed sibling modules

### Requirement: Core source tree is at most 12 files

The total count of Python source files at the top level of `src/a2kit/` (i.e. `src/a2kit/*.py`, excluding `__init__.py` and the `packages/` subtree) SHALL be at most 12.

#### Scenario: Core file count under threshold
- **WHEN** `find src/a2kit -maxdepth 1 -type f -name "*.py" -not -name "__init__.py" | wc -l` is run after the change
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
