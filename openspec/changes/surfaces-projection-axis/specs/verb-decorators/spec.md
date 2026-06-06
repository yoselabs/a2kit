## MODIFIED Requirements

### Requirement: `visibility` kwarg controls transport mounting tier

The `visibility` kwarg SHALL be removed from the verb decorators. Surface
placement and advertisement are governed solely by the `surfaces` kwarg
(see capability `surfaces-projection`), which assigns each registered
surface one of three states `ABSENT | LISTED | UNLISTED`. The former
`visibility` tiers map onto the matrix as follows:

- `visibility="hidden"` → a present-but-hidden state, spelled
  `surfaces={<surface>: "unlisted"}` (`UNLISTED`: mounted + callable,
  absent from listing/help/schema).
- `visibility="cli"` → CLI-only, spelled `surfaces=("cli",)` (`LISTED`
  on the CLI, `ABSENT` on every network surface).
- `visibility="all"` → advertised everywhere, spelled by omitting
  `surfaces=` or listing the surfaces explicitly (`LISTED`).

Passing `visibility=` to any verb decorator SHALL raise `TypeError` at
decoration time. The error message SHALL name `surfaces=` as the
replacement and SHALL give the mechanical rewrite for the supplied value
(e.g. `visibility="cli"` → `surfaces=("cli",)`). A Router class attribute
named `visibility` is likewise retired in favor of a `surfaces`-shaped
class default; the per-verb `surfaces=` kwarg overrides the class default.

#### Scenario: `visibility=` is rejected with a migration hint

- **GIVEN** a verb decorator `@a2kit.write`
- **WHEN** a tool is decorated `@a2kit.write(visibility="cli")`
- **THEN** a `TypeError` is raised at decoration time
- **AND** the message names `surfaces=` as the replacement
- **AND** the message gives the rewrite `surfaces=("cli",)`

#### Scenario: hidden tier maps to UNLISTED via dict

- **GIVEN** a verb formerly authored `@a2kit.write(visibility="hidden")`
- **WHEN** it is migrated to `@a2kit.write(surfaces={"cli": "unlisted"})`
- **THEN** the resolved state is `UNLISTED` on `cli`
- **AND** the verb is callable on the CLI but absent from `--help`
- **AND** the verb is `ABSENT` on every network surface

#### Scenario: cli tier maps to single-surface tuple

- **GIVEN** a verb formerly authored `@a2kit.read(visibility="cli")`
- **WHEN** it is migrated to `@a2kit.read(surfaces=("cli",))`
- **THEN** the resolved state is `LISTED` on `cli`
- **AND** the verb is `ABSENT` on every network surface

#### Scenario: all tier is the default

- **GIVEN** a verb formerly authored `@a2kit.read(visibility="all")`
- **WHEN** it is migrated by omitting `surfaces=`
- **THEN** the resolved state is `LISTED` on every registered surface

### Requirement: expose= validates against the live surface registry

The `expose=` kwarg SHALL be removed from the verb decorators
(`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`). Surface presence is
expressed by the `surfaces=` kwarg (see capability `surfaces-projection`):
a tuple of names resolves to `LISTED` on those names and `ABSENT`
elsewhere; a dict assigns explicit per-surface state.

The surface **names** used in `surfaces=` SHALL be validated against the
set of currently-registered surface names. The set MUST be obtained at
decoration time from a kernel-layer name registry that is kept in sync
with `SURFACE_REGISTRY` by a side-effect of `register_surface()`. The
literal `frozenset({"mcp", "api"})` MUST NOT appear in the verb-decorator
validation path. An unregistered name (whether in a tuple or as a dict
key) SHALL raise `TypeError` enumerating the registered names.

Passing `expose=` to any verb decorator SHALL raise `TypeError` at
decoration time, naming `surfaces=` as the replacement (e.g.
`expose=("mcp",)` → `surfaces=("mcp",)`).

#### Scenario: A registered surface name is accepted

- **GIVEN** the MCP and HTTP packages are imported (their surfaces self-register)
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("mcp",))`
- **THEN** the decorator does not raise

#### Scenario: An unregistered surface name is rejected with an enumerated message

- **GIVEN** the MCP and HTTP packages are imported
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("foo",))`
- **THEN** the decorator raises `TypeError`
- **AND** the error message enumerates the currently-registered surface names (e.g. "Registered surfaces: ('mcp', 'api')")
- **AND** the error message does not embed a hardcoded surface name list

#### Scenario: A newly-registered surface name is accepted without code changes to verbs

- **GIVEN** a test fixture registers a synthetic `StubSurface(name="test")`
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("test",))`
- **THEN** the decorator does not raise
- **AND** no edits to `src/a2kit/_verbs.py` were required

#### Scenario: Empty registry raises an actionable message

- **GIVEN** no Surface implementations have been imported
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("mcp",))`
- **THEN** the decorator raises `TypeError`
- **AND** the message instructs the author to import a surface-mounting package (e.g. `a2kit.packages.mcp`)

#### Scenario: `expose=` is rejected with a migration hint

- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** a `TypeError` is raised at decoration time
- **AND** the message names `surfaces=` as the replacement (`surfaces=("mcp",)`)
