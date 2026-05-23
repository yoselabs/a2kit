# principal-type Specification

## Purpose

`Principal` is the framework-owned, substrate-neutral identity record carried into `call_scope`. Owning it inside the framework (not inside any auth wrapper) lets every downstream consumer — tool bodies, `authorize=` callables, audit sinks — resolve `principal: Principal` by type annotation alone, and lets auth wrappers stay producers rather than redefining the type.

## Requirements
### Requirement: `Principal` is owned by the framework, not the auth wrapper

`Principal` SHALL be defined as a frozen dataclass in `a2kit.packages.context.principal`: `{subject: str, scopes: frozenset[str], claims: Mapping[str, Any], issued_by: str, raw_token: str | None}`. It SHALL be re-exported from `a2kit.packages.context` and lazily from top-level `a2kit.Principal`. Auth wrappers (defined in the separate `add-auth` change) SHALL produce `Principal` instances; they SHALL NOT define their own `Principal` type.

#### Scenario: Principal frozen

- **GIVEN** `p = Principal(subject="u1", scopes=frozenset(), claims={}, issued_by="test", raw_token=None)`
- **WHEN** code attempts `p.subject = "u2"`
- **THEN** `FrozenInstanceError` is raised

#### Scenario: Principal lazy at top level

- **GIVEN** a fresh interpreter
- **WHEN** `import a2kit` runs
- **THEN** `"Principal" not in a2kit.__dict__`
- **WHEN** `a2kit.Principal` is then accessed
- **THEN** the attribute resolves to `a2kit.packages.context.Principal`
