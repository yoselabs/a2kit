## MODIFIED Requirements

### Requirement: `_meta.health` SHALL install exclusively via `@app.health_check`

The synthetic `_meta.health` tool SHALL install as a side effect of
the first `@app.health_check` registration on an `App`. The install
SHALL be idempotent — subsequent `@app.health_check` calls SHALL
register additional checks without re-installing the synthetic
router. Apps with zero registered checks SHALL NOT have
`_meta.health` exposed; the synthetic router exists only when at
least one check exists.

The previous `App(health_tool=True)` install path SHALL NOT exist.
Constructing `App(...)` with that keyword SHALL raise the standard
unexpected-kwarg `TypeError` (naming the offending kwarg + the
CHANGELOG); the bespoke `@app.health_check` hint is swept under the
tombstone sunset rule (`AGENTS.md` §1) and `health_tool` falls through
to `App.__init__`'s generic kwarg rejection.

#### Scenario: First @app.health_check installs the synthetic tool

- **GIVEN** `app = a2kit.App("a")` (no checks yet)
- **WHEN** `@app.health_check` is applied to a function for the first time
- **THEN** `_meta.health` becomes invocable on the app's MCP/CLI surface
- **AND** `app.tools()` includes the synthetic tool descriptor

#### Scenario: Repeated @app.health_check is idempotent

- **GIVEN** an app with two `@app.health_check`-decorated functions registered
- **WHEN** the app is inspected
- **THEN** exactly one `_meta.health` tool descriptor exists
- **AND** both checks fire when `_meta.health` is invoked

#### Scenario: `health_tool=True` raises the generic unexpected-kwarg TypeError

- **GIVEN** code `a2kit.App("a", health_tool=True)`
- **WHEN** the constructor evaluates
- **THEN** `TypeError` is raised naming `health_tool` as an unexpected kwarg and pointing at the CHANGELOG
- **AND** no bespoke `health_check` hint string is required

#### Scenario: No checks → no synthetic tool

- **GIVEN** `app = a2kit.App("a")` with no `@app.health_check` registrations
- **WHEN** the app is inspected
- **THEN** `_meta.health` is NOT present in `app.tools()`
- **AND** invoking `_meta.health` over MCP returns the standard "unknown tool" error
