## ADDED Requirements

### Requirement: every source file has a mirror test file

For every `src/a2kit/<path>/<file>.py` (where `<file>.py` is neither
`__init__.py` nor `__main__.py`, and the file is not in the
A2K-TEST-MIRROR allow-list), a corresponding test file SHALL exist
at `tests/<path>/test_<file>.py`.

#### Scenario: Mirror exists for every source file
- **WHEN** the source tree and test tree are inspected after the change
- **THEN** for every non-exempt source file, the mirror test file
  exists at the deterministic path

#### Scenario: Lint rule fires on missing mirror
- **WHEN** `uv run a2kit lint static src/ tests/` runs against a tree
  where a non-exempt source file lacks its mirror
- **THEN** rule **A2K-TEST-MIRROR** fires, identifying the missing
  test file path

### Requirement: A2K-TEST-MIRROR allow-list is explicit

The lint rule SHALL maintain an explicit allow-list of source files
exempt from the mirror requirement. Each entry SHALL have a
documented rationale.

#### Scenario: Allow-list is in source
- **WHEN** the lint rule's source is inspected
- **THEN** an explicit module-level constant lists allow-listed paths
  with rationale per entry (Protocol, pure-data class, namespace
  `__init__`, etc.)

#### Scenario: Default allow-list contents
- **WHEN** the rule first ships
- **THEN** the allow-list contains at least:
  `src/a2kit/__init__.py`, `src/a2kit/__main__.py`,
  `src/a2kit/runtime.py` (Protocol), `src/a2kit/metadata.py`
  (frozen dataclass with no testable behavior beyond construction)

### Requirement: no empty test files

Every test file under `tests/` SHALL contain at least one function
whose name starts with `test_`. Empty mirror stubs are not allowed.

#### Scenario: Empty test file fires lint
- **WHEN** `tests/<path>/test_<file>.py` exists but contains no
  `def test_*` function
- **THEN** A2K-TEST-MIRROR fires with a "stub mirror needs at least
  one test" message

### Requirement: deterministic source → test path mapping

The mapping from source path to test path SHALL be deterministic and
documented in the spec:

```
src/a2kit/foo.py                        → tests/test_foo.py
src/a2kit/packages/cli/builder.py       → tests/packages/cli/test_builder.py
src/a2kit/packages/lint/rules/di.py     → tests/packages/lint/rules/test_di.py
```

#### Scenario: Mapping for top-level core files
- **WHEN** a source file lives at `src/a2kit/<file>.py`
- **THEN** its mirror is `tests/test_<file>.py`

#### Scenario: Mapping for plugin packages
- **WHEN** a source file lives at `src/a2kit/packages/<pkg>/<file>.py`
- **THEN** its mirror is `tests/packages/<pkg>/test_<file>.py`

#### Scenario: Mapping for nested rule subpackages
- **WHEN** a source file lives at `src/a2kit/packages/lint/rules/<file>.py`
- **THEN** its mirror is `tests/packages/lint/rules/test_<file>.py`

### Requirement: test-only modules are catalogued

Test files that have no source twin (e.g. `test_cold_start.py`,
`test_type_correctness_gate.py`, `conftest.py`) SHALL be listed in a
`tests/_test_only.txt` manifest or a `[tool.a2kit.test-mirror].test_only`
config block. The lint rule reads this list and does not flag these
files.

#### Scenario: Test-only manifest exists
- **WHEN** the project root is inspected
- **THEN** either `tests/_test_only.txt` or
  `pyproject.toml [tool.a2kit.test-mirror] test_only = [...]` exists,
  enumerating the test-only files
