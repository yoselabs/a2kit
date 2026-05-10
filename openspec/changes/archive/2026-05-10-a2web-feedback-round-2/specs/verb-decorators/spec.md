## ADDED Requirements

### Requirement: Verb decorators accept MCP annotation kwargs

`@a2kit.read`, `@a2kit.write`, and `@a2kit.tool` SHALL accept the MCP-annotation kwargs `idempotent: bool`, `open_world: bool`, and `title: str | None` (and `destructive: bool` on `@write` and `@tool`), forwarding them to the constructed `ToolAnnotations`.

#### Scenario: read with all annotation kwargs

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True, open_world=True, title="Fetch")`
- **THEN** the stamped `A2KitMeta.annotations` carries `ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=True, title="Fetch")`

#### Scenario: write with destructive override

- **WHEN** a tool is decorated `@a2kit.write(destructive=False, idempotent=True, title="Mark Complete")`
- **THEN** the annotations carry `readOnlyHint=False, destructiveHint=False, idempotentHint=True, title="Mark Complete"`

### Requirement: Verb decorators reject incompatible annotation kwargs

`@a2kit.read` SHALL raise `TypeError` if `destructive=` is passed (only meaningful on `@write` / `@tool`).

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb
