## ADDED Requirements

### Requirement: `surface=` selection removes the other surfaces

A `surface=` selector SHALL narrow the descriptor's source surface matrix (`extras.surfaces`), not merely the derived `expose` tuple, so that every surface builder agrees on placement. For an include set, each network surface (`mcp`/`api`) not in the include set SHALL be set to `ABSENT`; each excluded surface SHALL be set to `ABSENT`. The `cli` surface is not a `--select` target and SHALL be left unchanged. The selector SHALL also apply to synthetic `_meta.*` tools (e.g. `_meta.health`), so a selected surface actually removes the others rather than being kept alive by a framework-internal tool. A descriptor whose network surfaces all become `ABSENT` SHALL be dropped.

#### Scenario: MCP-only select drops the REST mount even with a health check

- **GIVEN** an `App` with a `@app.health_check` registration and a `@a2kit.read()` projection tool
- **WHEN** it is built with `select=["surface=mcp"]` and mounted via `build_parent_app`
- **THEN** the parent mounts `/mcp` only — `/api` is not mounted
- **AND** a `GET /api/openapi.json` against the mounted app is not served

#### Scenario: the source matrix is narrowed, not just expose

- **GIVEN** the same `App` built with `select=["surface=mcp"]`
- **WHEN** the projection tool's descriptor is inspected
- **THEN** `advertised_on(matrix_for(descriptor._meta.extras), "api")` is `False`
- **AND** `descriptor.expose` equals `("mcp",)`

#### Scenario: the synthetic `_meta.health` tool is narrowed like any other

- **GIVEN** an `App` with a `@app.health_check` registration built with `select=["surface=mcp"]`
- **WHEN** the `_meta.health` descriptor is inspected
- **THEN** its `expose` equals `("mcp",)`
- **AND** its matrix no longer advertises `api`

#### Scenario: cli matrix state is preserved under a network surface select

- **GIVEN** a projection tool LISTED on `mcp`, `api`, and `cli`
- **WHEN** it is built with `select=["surface=mcp"]`
- **THEN** its matrix still mounts `cli` (a `--select surface=` narrow touches only the network surfaces)

#### Scenario: api-only select is the symmetric case

- **GIVEN** an `App` with a `@app.health_check` registration and a projection tool
- **WHEN** it is built with `select=["surface=api"]` and mounted via `build_parent_app`
- **THEN** the parent mounts `/api` only — `/mcp` is not mounted
