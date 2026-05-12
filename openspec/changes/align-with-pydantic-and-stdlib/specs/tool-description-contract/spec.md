# tool-description-contract — align-with-pydantic-and-stdlib delta

## MODIFIED Requirements

### Requirement: Per-parameter descriptions via `pydantic.Field`

The system SHALL accept `Annotated[T, pydantic.Field(description="...")]`
on tool kwargs and forward the description to the MCP parameter
schema and CLI option help. The annotation pattern SHALL be the
same one used by Pydantic body models, with no a2kit-specific
wrapper. The library SHALL NOT expose `a2kit.Param` — tool authors
import `pydantic.Field` directly.

#### Scenario: Field description forwarded to MCP schema

- **WHEN** a tool has `url: Annotated[str, pydantic.Field(description="Absolute http(s) URL.")]`
- **THEN** the MCP tool input schema's `properties.url.description` is `"Absolute http(s) URL."`

#### Scenario: Field description forwarded to click help

- **WHEN** the same parameter is invoked via the CLI
- **THEN** `<app> <tool> --help` shows `--url ...` with the description string

#### Scenario: Extra Field metadata is forwarded

- **WHEN** a tool has `count: Annotated[int, pydantic.Field(description="Number of items.", ge=1, le=100, examples=[10])]`
- **THEN** the MCP input schema's `properties.count` carries
  `description`, `minimum=1`, `maximum=100`, and `examples=[10]`,
  produced by pydantic's standard FieldInfo schema generation

### Requirement: Pydantic Field descriptions continue to work for body models

The system SHALL preserve the existing behavior where a tool kwarg
that is a Pydantic model carries field descriptions via
`pydantic.Field(description=...)`. The same surface — `pydantic.Field`
inside `Annotated[T, ...]` — covers both direct tool kwargs and
nested body-model fields, with no separate marker for either case.

#### Scenario: model body kwarg uses Field descriptions

- **WHEN** a tool kwarg is a Pydantic model whose fields use `Field(description="...")`
- **THEN** those descriptions appear in the MCP input schema's nested object properties unchanged

#### Scenario: direct kwarg and body-model field share the same annotation surface

- **WHEN** the same `pydantic.Field(description="...")` annotation
  is applied to a direct `Annotated[str, Field(...)]` tool kwarg
  and to a `BaseModel` class attribute via `Field(...)`
- **THEN** both descriptions surface identically in the generated
  MCP input schema — no separate code path or marker is needed for
  the kwarg case

## REMOVED Requirements

### Requirement: Per-parameter descriptions via `a2kit.Param`

**Reason for removal**: `a2kit.Param(description=, **extras)` was a
one-line wrapper that called `pydantic.Field(description=, **extras)`
and returned a `FieldInfo`. The wrapper added no capability beyond
what `pydantic.Field` already provides, and Pydantic's `Annotated[T, Field(...)]`
pattern is the canonical Python convention for attaching schema
metadata. The positional-shorthand form (`Param("desc")`) and the
positional/keyword collision `TypeError` were cosmetic conveniences
that came at the cost of teaching consumers two ways to do the same
thing. The library is pre-1.0 and `Param` was added two minor
versions before this removal; no deprecation cycle is offered.

**Migration**:
- `a2kit.Param("desc")` → `pydantic.Field(description="desc")`
- `a2kit.Param(description="desc")` → `pydantic.Field(description="desc")`
- `a2kit.Param(description="desc", examples=[...])` → `pydantic.Field(description="desc", examples=[...])`

The MCP-schema-description and CLI-help-description scenarios are
preserved as scenarios on the "Per-parameter descriptions via
`pydantic.Field`" requirement above.
