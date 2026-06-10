## MODIFIED Requirements

### Requirement: The old `(expose, visibility)` pair maps mechanically onto the matrix

The retired `expose=` / `visibility=` pair SHALL be **removed** from the verb
decorators — there SHALL be no transitional shim and no `DeprecationWarning`;
passing either kwarg SHALL raise the language-default unexpected-keyword
`TypeError`. The
mapping below is the **migration recipe** (recorded in the CHANGELOG) so
downstream consumers can rewrite each decorated verb deterministically. Because
legacy `visibility="all"` always also mounted the verb on the CLI (the
"god-view"), the faithful rewrite preserves CLI presence — a blind
`expose→surfaces` transliteration would silently drop the CLI mount:

- `expose=("mcp","api"), visibility="all"` → omit `surfaces=` (or `surfaces=("mcp","api","cli")`).
- `expose=("mcp",), visibility="all"` → `surfaces=("mcp","cli")` (CLI preserved).
- `expose=("api",), visibility="all"` → `surfaces=("api","cli")`.
- `visibility="cli"` (any `expose`) → `surfaces=("cli",)`.
- `visibility="hidden"` (any `expose`) → `surfaces={<surface>: "unlisted"}`.

`surfaces=` is the only placement axis; the resolved matrix is always computed
from it (or its omitted-default) at decoration time.

#### Scenario: legacy pair no longer resolves at decoration

- **GIVEN** a verb decorated `@a2kit.write(visibility="cli")` or `@a2kit.read(expose=("mcp",))`
- **WHEN** the module is imported
- **THEN** a `TypeError` is raised naming the offending kwarg as unexpected
- **AND** no legacy-mapping shim runs and no `DeprecationWarning` is emitted

#### Scenario: cli-only verb is authored as a single-surface tuple

- **WHEN** a verb is decorated `@a2kit.write(surfaces=("cli",))`
- **THEN** the resolved matrix is `LISTED` on `cli`, `ABSENT` on every network surface (no HTTP leak by construction)

#### Scenario: hidden verb is authored as a dict UNLISTED

- **WHEN** a verb is decorated `@a2kit.read(surfaces={"mcp": "unlisted"})`
- **THEN** the resolved matrix is `UNLISTED` on `mcp`, `ABSENT` elsewhere
