## ADDED Requirements

### Requirement: Living narrative docs have an automated symbol-drift gate

The repository SHALL include a test (`tests/test_docs_symbol_drift.py`) that
scans the living narrative docs and asserts every checkable code-font symbol
resolves on the live `a2kit` surface, so a rename or removal in code fails at
PR time rather than at consumer-migration time. The gate SHALL share one
extraction/resolution engine (`tests/support/symbol_drift.py`) with the
spec-drift gate — there SHALL NOT be a second copy of the extraction logic.

The doc set under the gate SHALL be the current-state living docs:
`ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`, and `docs/patterns/*.md`.
`docs/adr/*.md` SHALL be EXCLUDED by design — an ADR is a historical record
and rightly cites the names it removed; gating it would punish correct
history.

The gate SHALL fail the `make lint` target on any drift. Its allowlist SHALL
hold only genuine non-symbols (logger names, sentinel marker strings that a
lint rule greps for); a reference to a removed API is a doc to fix, not an
allowlist entry to add.

#### Scenario: All living-doc symbols resolve

- **GIVEN** living docs whose every claimed public symbol exists in the live code surface
- **WHEN** `pytest tests/test_docs_symbol_drift.py` runs
- **THEN** the test passes

#### Scenario: Stale symbol in a living doc is caught

- **GIVEN** `OPERATIONAL_CONTRACTS.md` cites a removed `a2kit.<old>` emission symbol after the surface moved it to `a2kit.log`
- **WHEN** the gate runs
- **THEN** it fails with a message naming the symbol, the doc and line, and the missing resolution

#### Scenario: ADR bodies are not scanned

- **GIVEN** an ADR body under `docs/adr/` that cites a removed symbol (e.g. `a2kit.AppBuilder`) as the history of a decision
- **WHEN** the docs drift gate runs
- **THEN** the ADR is not scanned and the citation does not fail the gate

#### Scenario: Gate runs under make lint

- **WHEN** a contributor runs `make lint`
- **THEN** the docs symbol-drift test executes as part of the gate
- **AND** any drift fails the lint target

## MODIFIED Requirements

### Requirement: README accurately reflects the v0.33 public surface

Human-readable documentation SHALL NOT reference symbols or example call shapes that do not exist on the live code surface.
This applies to the living narrative docs — `README.md`, `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`, and `docs/patterns/*.md`. A documented example that names a removed or renamed API teaches a consumer to write code that fails, so doc-vs-code parity is a correctness property of the docs, not a cosmetic one. ADR bodies under `docs/adr/` are EXEMPT from this parity standard: an ADR is a historical record and rightly cites the names its decision removed.

The release pass SHALL, for `README.md`, ensure that:

- The lifecycle path documented is the canonical one — `App(lifespan=async_cm)` — with no decorator-form startup or shutdown hooks claimed on `App` or `Router`.
- `Surface` Flag-enum claims are replaced with the actual `Visibility = Literal["hidden", "cli", "all"]` form.
- The verb decorators are documented in their current form only, with no bare-verb decorator and no `name=` or `tags=` kwargs on them.
- Tool introspection is documented as `app.tools()`, the single live accessor.
- The connection-wiring example uses the single-call `install_connections(app, ConnT)` form.
- DI registration examples use the live `app.provide(T, factory)` method-call form only.
- The `LDD` acronym is spelled out at first mention.
- The `list_` trailing-underscore convention is documented.
- The default connection-store path is documented.

Beyond the README pass, the parity standard SHALL hold for the other living narrative docs. Specifically, no living-narrative doc (README, ANTIPATTERNS, OPERATIONAL_CONTRACTS, docs/patterns) SHALL reference, in prose, a markdown table, or a fenced example, any API removed from the live surface. The class of removed APIs covered includes the symbols dropped across v0.33–v0.41: the old bare verb decorator, the capability-tag types now superseded by plain strings, the `App(name, health_tool=True)` constructor form, the old decorator-form lifecycle hooks and the old DI-registration verb together with the private singleton-cache attribute, the dropped TOON encoder and its format hint, the method-form LDD primitives now provided as `a2kit.log` free functions, and the singular verb-kwarg form whose live spelling is `reports=` (plural). ADR bodies are exempt from the removed-API references standard (history), but ADR frontmatter `status` SHALL reflect reality: an ADR whose decision has shipped SHALL carry `status: accepted`, not `status: proposed`.

#### Scenario: No phantom symbols in README

- **GIVEN** the current `README.md`
- **WHEN** the symbol-drift test runs
- **THEN** every claimed `@app.X` / `App.X` / `Router.X` / `a2kit.X` / `a2kit.<submodule>.X` reference resolves on the live surface
- **AND** no reference to a symbol removed across v0.33–v0.41 remains — including the old lifecycle-hook decorators, the bare verb decorator, the retired tool-introspection accessor, and the removed `Surface` Flag-enum members

#### Scenario: Non-README docs name only live APIs

- **GIVEN** `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`, and `docs/patterns/*.md`
- **WHEN** the docs symbol-drift gate checks each example call shape and symbol reference against the live surface
- **THEN** every cited symbol resolves on the live surface
- **AND** no example names an API removed across v0.33–v0.41 — the old capability-tag types, the bare verb decorator, the removed constructor form, the old lifecycle hooks, the old DI-registration verb, the private singleton cache, a TOON encoder, the method-form LDD primitives, or the singular verb-kwarg form

#### Scenario: ADR status reflects shipped reality

- **GIVEN** ADR 0013 (`adopt-fastmcp-codemode`) and ADR 0014 (`consumer-aware-rendering`), whose decisions have shipped in code
- **WHEN** their frontmatter `status` is inspected
- **THEN** both read `status: accepted`
- **AND** `docs/adr/INDEX.md` has been regenerated by `make adr-index` to match
