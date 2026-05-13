## ADDED Requirements

### Requirement: README symbol-drift CI gate

The repository SHALL include a test (`tests/test_readme_symbol_drift.py`) that parses `README.md` and asserts every claimed public symbol resolves on the live module surface. The test SHALL fail the `make lint` target on any drift between README and runtime, so documentation regressions are caught at PR time rather than at consumer-migration time.

**Symbol patterns to check.** The test SHALL extract symbol references from the following loci in `README.md`:

- Fenced code blocks (```` ```python ... ``` ````, ```` ```bash ... ``` ````, and unmarked fenced blocks).
- Inline code spans (`` `name` ``) that match one of the symbol patterns below.

**Patterns the test SHALL resolve:**

- `a2kit.X` and `@a2kit.X` — must `hasattr(a2kit, "X")` on import. Examples: `a2kit.App`, `a2kit.Router`, `@a2kit.read`, `a2kit.ToolContext`, `a2kit.HealthResult`.
- `a2kit.<submodule>.Y` and `@a2kit.<submodule>.Y` — must resolve via `importlib.import_module("a2kit.<submodule>")` followed by `hasattr(mod, "Y")`. Examples: `a2kit.ldd.event`, `a2kit.testing.client`.
- `App.method` and `app.method` — must `hasattr(a2kit.App, "method")`. Examples: `App.add_router`, `app.provide`, `app.singleton`, `app.tools`.
- `Router.attribute` — must `hasattr(a2kit.Router, "attribute")`. Examples: `Router.slug`, `Router.tools`, `Router.enrichers`, `Router.providers`.
- `@app.X` — must `hasattr(a2kit.App, "X")`. Examples: `@app.health_check`.

**Tolerated false positives.** The test MAY report false positives on prose mentions of identical strings (e.g., the word "App" in body text matching some unrelated symbol). False positives are acceptable because they would also be valid claims if they did exist. False negatives (symbol claimed in prose without backticks) are tolerated for the initial implementation.

**Failure mode.** A failing assertion SHALL name the unresolved symbol, the line in `README.md` where it appeared, and the resolution that was attempted (e.g., `hasattr(a2kit, "on_startup") is False`).

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

The `README.md` file SHALL NOT reference symbols that do not exist on the live code surface. Specifically, the v0.33 release pass SHALL:

- Remove all references to `@app.on_startup` and `@app.on_shutdown` (removed in v0.31; canonical lifecycle path is `App(lifespan=async_cm)`).
- Remove references to `Router.on_startup` and `Router.on_shutdown` methods (never existed on the public surface).
- Replace `Surface` Flag-enum claims with the actual `Visibility = Literal["hidden", "cli", "all"]` form.
- Remove references to `@a2kit.tool` bare verb (removed in v0.33).
- Remove references to `name=` and `tags=` kwargs on verb decorators (removed in v0.33).
- Remove references to `app.tool_descriptors()` (collapsed into `app.tools()` in v0.33).
- Update connection-wiring example to use the single-call `install_connections(app, ConnT)` form (no separate `add_cli(connections_cli(...))` if already covered by `install_connections`).
- Update `app.singleton` examples to method-call form only (no decorator form).
- Spell out the `LDD` acronym at first mention.
- Document the `list_` trailing-underscore convention.
- Document the default connection-store path.

#### Scenario: No phantom symbols in README

- **GIVEN** the v0.33 `README.md`
- **WHEN** the symbol-drift test runs
- **THEN** every claimed `@app.X` / `App.X` / `Router.X` / `a2kit.X` / `a2kit.<submodule>.X` reference resolves
- **AND** no `@app.on_startup`, `@app.on_shutdown`, `@a2kit.tool`, `app.tool_descriptors`, `Surface.CLI`, `Surface.MCP`, `Surface.ALL` references remain
