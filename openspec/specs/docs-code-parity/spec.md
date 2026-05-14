# docs-code-parity Specification

## Purpose
TBD - created by archiving change prettify-consumption-interface. Update Purpose after archive.
## Requirements
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

### Requirement: Canonical-type method drift gate SHALL extend the README symbol-drift check

The CI lint stage SHALL fail when a method name accessed on a
documented canonical type in `README.md` does not exist on the
live class. The canonical types under coverage SHALL include at
minimum `TestClient`, `App`, `Router`, the `ToolContext` re-export,
and the verb decorators `read` / `write` / `list_`. The gate
SHALL parse fenced ```python``` code blocks, AST-walk for
`ast.Attribute` nodes whose `obj_name` resolves to a canonical type
(directly or via variable-name registration within the same block),
and assert `hasattr(canonical_type, attr_name)`.

#### Scenario: Renamed canonical method fails the gate

- **GIVEN** README contains `await client.call(tool, msg="hi")` and `TestClient.call` does not exist on the live class
- **WHEN** `make lint` runs
- **THEN** the drift-gate test fails with a message naming `client.call` and the README location where the call is documented

#### Scenario: Aliased canonical method passes the gate

- **GIVEN** README contains `await client.invoke(tool, msg="hi")` and `TestClient.invoke` exists on the live class
- **WHEN** the gate runs
- **THEN** the access resolves and the gate passes for that block

#### Scenario: Variable name in code block registers as a canonical type

- **GIVEN** a README code block contains `client = a2kit.testing.client(app)` followed by `await client.invoke(...)`
- **WHEN** the gate parses the block
- **THEN** the assignment registers `client` as `TestClient` for the remainder of the block, and `client.invoke` resolves against `TestClient.invoke`

### Requirement: Canonical-API call-shape exerciser SHALL run as a sister test

`tests/test_canonical_apis.py` SHALL exist and SHALL exercise the
documented call shapes end-to-end with a small fixture app. The
test SHALL run as part of `make lint` (alongside the README
drift gate) so silent renames-without-test-updates fail at CI
time. Coverage SHALL include at minimum:

- `TestClient.invoke(...)` and `TestClient.call_wire(...)`
- `App.singleton(T, factory)` and `App.singleton(T, factory, teardown=...)`
- `@a2kit.read()`, `@a2kit.write(...)`, `@a2kit.list_()`
- `Router` subclass with `slug = "x"` and `tools = (...)`

The test SHALL use bind-against-live-types rather than
text-matching, so a rename that preserves observable behavior
under a new name (but breaks the documented call shape) fails.

#### Scenario: Each canonical call shape runs successfully

- **GIVEN** the fixture app from `test_canonical_apis.py`
- **WHEN** the test exercises each documented call shape
- **THEN** every call succeeds (no AttributeError, no TypeError, no signature mismatch)

#### Scenario: Removed surface fails the test loudly

- **GIVEN** a previously-documented call shape that no longer exists on the canonical type
- **WHEN** the test runs after the removal
- **THEN** the test fails with a message naming the removed method

