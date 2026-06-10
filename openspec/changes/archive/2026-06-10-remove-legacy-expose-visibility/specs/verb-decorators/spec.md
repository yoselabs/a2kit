## MODIFIED Requirements

### Requirement: `@a2kit.list_(...)` consolidates list-view settings

`@a2kit.list_(*default_fields: str, page_size: int | None = None, selectable_fields: tuple[str, ...] | None = None, name: str | None = None, reports: type | None = None, idempotent: bool = False, open_world: bool = False, title: str | None = None, surfaces: ... = UNSET)` SHALL accept the same semantic-flag and routing kwargs as the other verb decorators (`read`, `write`), in addition to its list-shape-specific kwargs (`*default_fields`, `page_size`, `selectable_fields`). Surface placement is governed solely by `surfaces=` (capability `surfaces-projection`); the legacy `visibility=` / `expose=` kwargs are NOT accepted.

`destructive=` SHALL NOT be accepted on `@a2kit.list_` (list is a read shape; matches the `@a2kit.read` contract — passing `destructive=True` raises `TypeError`).

#### Scenario: `title=` and `idempotent=` propagate to ToolAnnotations
- **WHEN** a tool is decorated `@a2kit.list_("id", title="Projects", idempotent=True)`
- **THEN** `meta.annotations.title == "Projects"`
- **AND** `meta.annotations.idempotentHint is True`
- **AND** `meta.annotations.readOnlyHint is True`

#### Scenario: `visibility=` is rejected as an unknown kwarg
- **WHEN** a tool is decorated `@a2kit.list_("id", visibility="cli")`
- **THEN** `TypeError` is raised naming `visibility` as an unexpected keyword argument
- **AND** no `meta.extras.visibility` field exists (use `surfaces=("cli",)`)

#### Scenario: `destructive=True` is rejected
- **WHEN** a tool is decorated `@a2kit.list_("id", destructive=True)`
- **THEN** `TypeError` is raised (list is read-shaped)

### Requirement: `visibility` kwarg controls transport mounting tier

The `visibility` and `expose` kwargs SHALL NOT exist on the verb decorators. Surface placement and advertisement are governed solely by the `surfaces` kwarg (see capability `surfaces-projection`), which assigns each registered surface one of three states `ABSENT | LISTED | UNLISTED`. The former `visibility` tiers map onto the matrix as a migration recipe (recorded in the CHANGELOG):

- `visibility="hidden"` → `surfaces={<surface>: "unlisted"}` (`UNLISTED`: mounted + callable, absent from listing/help/schema).
- `visibility="cli"` → `surfaces=("cli",)` (`LISTED` on the CLI, `ABSENT` on every network surface).
- `visibility="all"` → omit `surfaces=` (default `LISTED` on every registered surface).

Passing `visibility=` or `expose=` to any verb decorator SHALL raise the language-default unexpected-keyword-argument `TypeError` (the kwargs are absent from the signature — caught statically by type checkers and at decoration time at runtime). No bespoke migration hint is embedded; the rewrite recipe lives in the CHANGELOG. A Router class attribute named `visibility` is likewise retired with **no** class-level surface default — surface placement is per-verb `surfaces=`, defaulting to `LISTED` on every surface when omitted.

#### Scenario: `visibility=` is rejected as an unknown kwarg
- **GIVEN** a verb decorator `@a2kit.write`
- **WHEN** a tool is decorated `@a2kit.write(visibility="cli")`
- **THEN** a `TypeError` is raised naming `visibility` as an unexpected keyword argument
- **AND** the decorator signature does not declare `visibility`

#### Scenario: `expose=` is rejected as an unknown kwarg
- **GIVEN** a verb decorator `@a2kit.read`
- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** a `TypeError` is raised naming `expose` as an unexpected keyword argument

#### Scenario: cli tier maps to single-surface tuple
- **GIVEN** a verb formerly authored `@a2kit.read(visibility="cli")`
- **WHEN** it is migrated to `@a2kit.read(surfaces=("cli",))`
- **THEN** the resolved state is `LISTED` on `cli`
- **AND** the verb is `ABSENT` on every network surface

#### Scenario: all tier is the default
- **GIVEN** a verb formerly authored `@a2kit.read(visibility="all")`
- **WHEN** it is migrated by omitting `surfaces=`
- **THEN** the resolved state is `LISTED` on every registered surface
