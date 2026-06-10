## MODIFIED Requirements

### Requirement: README symbol-drift CI gate

The repository SHALL include a test (`tests/test_readme_symbol_drift.py`) that parses `README.md` and asserts every claimed public symbol resolves on the live module surface.
The test SHALL fail the `make lint` target on any drift between README and runtime, so documentation regressions are caught at PR time rather than at consumer-migration time.

**Symbol patterns to check.** The test SHALL extract symbol references from the following loci in `README.md`:

- Fenced code blocks (```` ```python ... ``` ````, ```` ```bash ... ``` ````, and unmarked fenced blocks).
- Inline code spans (`` `name` ``) that match one of the symbol patterns below.

**Patterns the test SHALL resolve:**

- `a2kit.X` and `@a2kit.X` — must `hasattr(a2kit, "X")` on import. Examples: `a2kit.App`, `a2kit.Router`, `@a2kit.read`, `a2kit.ToolContext`, `a2kit.HealthResult`.
- `a2kit.<submodule>.Y` and `@a2kit.<submodule>.Y` — must resolve via `importlib.import_module("a2kit.<submodule>")` followed by `hasattr(mod, "Y")`. Examples: `a2kit.log.info`, `a2kit.testing.client`.
- `App.method` and `app.method` — must `hasattr(a2kit.App, "method")`. Examples: `app.provide`, `app.tools`. A name that names a DI-registration verb other than the live one is not a valid claim — the live registration method is `app.provide`.
- `Router.attribute` — must `hasattr(a2kit.Router, "attribute")`. Examples: `Router.slug`, `Router.providers`. An attribute that does not exist on the live `Router` is not a valid claim.
- `@app.X` — must `hasattr(a2kit.App, "X")`. Examples: `@app.health_check`.

**Tolerated false positives.** The test MAY report false positives on prose mentions of identical strings. False positives are acceptable. False negatives (symbol claimed in prose without backticks) are tolerated for the initial implementation.

**Failure mode.** A failing assertion SHALL name the unresolved symbol, the line in `README.md` where it appeared, and the resolution that was attempted.

#### Scenario: All README symbols resolve

- **GIVEN** a `README.md` whose every claimed public symbol exists in the live code surface
- **WHEN** `pytest tests/test_readme_symbol_drift.py` runs
- **THEN** the test passes

#### Scenario: Stale symbol is caught

- **GIVEN** `README.md` claims, in a fenced code block or inline span, an `@app.X` lifecycle-hook decorator that does not exist on the live `a2kit.App`
- **WHEN** the test runs
- **THEN** it fails with a message naming the symbol, the README line, and the missing resolution

#### Scenario: Drift on submodule symbol is caught

- **GIVEN** `README.md` claims `a2kit.log.foo` but `a2kit.log` does not export `foo`
- **WHEN** the test runs
- **THEN** it fails with a message naming the symbol and the missing resolution

#### Scenario: Test runs under `make lint`

- **WHEN** a contributor runs `make lint`
- **THEN** the README symbol-drift test executes as part of the gate
- **AND** any drift fails the lint target
