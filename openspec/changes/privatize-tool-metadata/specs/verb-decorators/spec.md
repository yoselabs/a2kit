## ADDED Requirements

### Requirement: `get_meta` and `set_meta` are not public

`a2kit.metadata` SHALL NOT expose `get_meta` or `set_meta` as callable accessors. Their underscored counterparts (`_get_meta`, `_set_meta`) are module-private and restricted to the composition-path allowlist `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`.

The public-name shims SHALL raise `AttributeError` with a migration hint pointing at `AppRuntime.descriptor_for(name)` and `ToolDescriptor`. The shims SHALL not be removed entirely — they remain as a loud-failure surface so external code that previously imported them gets a clear error rather than a `NameError`.

#### Scenario: decorator stamps via private API

- **GIVEN** a verb decorator like `@a2kit.read(...)` is applied to a function
- **WHEN** the decorator stamps `A2KitMeta` on `fn.__a2kit__`
- **THEN** it uses `metadata._set_meta(fn, meta)` (private)
- **AND** no external module reads back via `get_meta` or `_get_meta`

#### Scenario: external import of get_meta fails loudly

- **GIVEN** a downstream package writes `from a2kit.metadata import get_meta`
- **WHEN** the package calls `get_meta(fn)`
- **THEN** `AttributeError` is raised with the migration hint
