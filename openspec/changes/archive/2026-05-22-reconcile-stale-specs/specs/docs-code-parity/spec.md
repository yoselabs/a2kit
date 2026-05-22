## MODIFIED Requirements

### Requirement: README symbol-drift CI gate

The repository SHALL include a test (`tests/test_readme_symbol_drift.py`) that parses `README.md` and asserts every claimed public symbol resolves on the live module surface. The test SHALL fail the `make lint` target on any drift between README and runtime, so documentation regressions are caught at PR time rather than at consumer-migration time.

**Symbol patterns to check.** The test SHALL extract symbol references from the following loci in `README.md`:

- Fenced code blocks (```` ```python ... ``` ````, ```` ```bash ... ``` ````, and unmarked fenced blocks).
- Inline code spans (`` `name` ``) that match one of the symbol patterns below.

**Patterns the test SHALL resolve:**

- `a2kit.X` and `@a2kit.X` — must `hasattr(a2kit, "X")` on import. Examples: `a2kit.App`, `a2kit.Router`, `@a2kit.read`, `a2kit.ToolContext`, `a2kit.HealthResult`.
- `a2kit.<submodule>.Y` and `@a2kit.<submodule>.Y` — must resolve via `importlib.import_module("a2kit.<submodule>")` followed by `hasattr(mod, "Y")`. Examples: `a2kit.ldd.event`, `a2kit.testing.client`.
- `App.method` and `app.method` — must `hasattr(a2kit.App, "method")`. Examples: `App.add_router`, `app.provide`, `app.tools`. (The dead name `app.singleton` is NOT a valid claim — the method is `app.provide`.)
- `Router.attribute` — must `hasattr(a2kit.Router, "attribute")`. Examples: `Router.slug`, `Router.tools`, `Router.enrichers`. (`Router.providers` is NOT a valid claim — no such attribute exists.)
- `@app.X` — must `hasattr(a2kit.App, "X")`. Examples: `@app.health_check`.

**Tolerated false positives.** The test MAY report false positives on prose mentions of identical strings. False positives are acceptable. False negatives (symbol claimed in prose without backticks) are tolerated for the initial implementation.

**Failure mode.** A failing assertion SHALL name the unresolved symbol, the line in `README.md` where it appeared, and the resolution that was attempted.

#### Scenario: All README symbols resolve

- **GIVEN** a `README.md` whose every claimed public symbol exists in the live code surface
- **WHEN** `pytest tests/test_readme_symbol_drift.py` runs
- **THEN** the test passes

#### Scenario: Stale symbol is caught

- **GIVEN** `README.md` claims `@app.on_startup` (in a fenced code block or inline span) but `a2kit.App` has no `on_startup` attribute
- **WHEN** the test runs
- **THEN** it fails with a message naming the symbol, the README line, and the missing resolution

#### Scenario: Drift on submodule symbol is caught

- **GIVEN** `README.md` claims `a2kit.ldd.foo` but `a2kit.ldd` does not export `foo`
- **WHEN** the test runs
- **THEN** it fails with a message naming the symbol and the missing resolution

#### Scenario: Test runs under `make lint`

- **WHEN** a contributor runs `make lint`
- **THEN** the README symbol-drift test executes as part of the gate
- **AND** any drift fails the lint target

### Requirement: README accurately reflects the v0.33 public surface

The `README.md` file SHALL NOT reference symbols that do not exist on the live code surface. The release pass SHALL keep the README free of removed surfaces, specifically:

- No references to `@app.on_startup` or `@app.on_shutdown` (these decorators do not exist on `App`; lifecycle is the async-context-manager protocol).
- No references to `Router.on_startup` / `Router.on_shutdown` methods.
- No references to a `Surface` Flag-enum; use the actual visibility form the code exposes.
- No references to a bare `@a2kit.tool` verb (removed in v0.33).
- No references to `name=` / `tags=` kwargs on verb decorators where the code does not accept them.
- No references to `app.tool_descriptors()`.
- DI-registration examples SHALL use `app.provide(...)` — `app.singleton(...)` is not a method on `App` and MUST NOT appear in any README example.
- The `list_` trailing-underscore convention SHALL be documented.

#### Scenario: No phantom symbols in README

- **GIVEN** the current `README.md`
- **WHEN** the symbol-drift test runs
- **THEN** every claimed `@app.X` / `App.X` / `Router.X` / `a2kit.X` / `a2kit.<submodule>.X` reference resolves
- **AND** no `@app.on_startup`, `@app.on_shutdown`, `@a2kit.tool`, `app.tool_descriptors`, or `app.singleton` reference remains

### Requirement: Canonical-API call-shape exerciser SHALL run as a sister test

`tests/test_canonical_apis.py` SHALL exist and SHALL exercise the documented call shapes end-to-end with a small fixture app. The test SHALL run as part of `make lint` (alongside the README drift gate) so silent renames-without-test-updates fail at CI time. Coverage SHALL include at minimum:

- `TestClient.invoke(...)` and `TestClient.call_wire(...)`
- `App.provide(T, factory)` and `App.provide(T, factory, per_call=True)` (the registration API — `App.singleton` does not exist)
- `@a2kit.read()`, `@a2kit.write(...)`, `@a2kit.list_()`
- `Router` subclass with `slug = "x"` and `tools = (...)`

The test SHALL bind against live types rather than text-matching, so a rename that preserves observable behavior under a new name (but breaks the documented call shape) fails.

#### Scenario: Each canonical call shape runs successfully

- **GIVEN** the fixture app from `test_canonical_apis.py`
- **WHEN** the test exercises each documented call shape
- **THEN** every call succeeds (no `AttributeError`, no `TypeError`, no signature mismatch)

#### Scenario: Removed surface fails the test loudly

- **GIVEN** a previously-documented call shape that no longer exists on the canonical type
- **WHEN** the test runs after the removal
- **THEN** the test fails with a message naming the removed method
