## MODIFIED Requirements

### Requirement: Test directory mirrors source structure

The `tests/` directory SHALL mirror the structure of `src/a2kit/`.
Every source file (excluding allow-listed Protocols, dataclasses,
`__init__.py`, and `__main__.py`) SHALL have a corresponding test
file at the deterministic mirror path.

This requirement is **enforced** by the A2K-TEST-MIRROR lint rule
(see `test-mirror-discipline` capability). It is not advisory.

The mapping is:

| Source path | Test path |
|---|---|
| `src/a2kit/foo.py` | `tests/test_foo.py` |
| `src/a2kit/packages/<pkg>/<file>.py` | `tests/packages/<pkg>/test_<file>.py` |
| `src/a2kit/packages/lint/rules/<file>.py` | `tests/packages/lint/rules/test_<file>.py` |

#### Scenario: Tests slice cleanly by package
- **WHEN** a developer runs `pytest tests/packages/connections/` after the change
- **THEN** the result exercises only the `packages/connections/` code paths

#### Scenario: Top-level modules have flat tests
- **WHEN** a top-level module like `tool.py` exists in `src/a2kit/`
- **THEN** `tests/test_tool.py` exists with at least one `def test_*`

#### Scenario: Plugin-package tests live under `tests/packages/`
- **WHEN** a plugin module like `mcp/server.py` exists at `src/a2kit/packages/mcp/server.py`
- **THEN** `tests/packages/mcp/test_server.py` exists with at least one `def test_*`

#### Scenario: Lint rule catches drift
- **WHEN** a new source file is added without its mirror
- **THEN** `make lint` fails with an A2K-TEST-MIRROR finding pointing at the missing test path

#### Scenario: Empty mirror files are forbidden
- **WHEN** a mirror test file exists but contains no `def test_*` function
- **THEN** A2K-TEST-MIRROR fires with a "stub mirror needs at least one test" message
