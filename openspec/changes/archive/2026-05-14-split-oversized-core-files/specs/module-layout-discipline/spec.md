# module-layout-discipline — split-oversized-core-files delta

## ADDED Requirements

### Requirement: DI factory-introspection helpers SHALL live in their own module

DI factory-introspection helpers (`Factory`, `UnresolvableType`, `_ParamSpec`, `_factory_callable`, `_factory_params`, `_is_primitive_or_external`) SHALL live in `src/a2kit/packages/di/_introspection.py` so `container.py` stays under the A2K014 SLOC budget without suppression.

#### Scenario: Introspection helpers importable from the sibling module

- **WHEN** consumer code or tests do `from a2kit.packages.di._introspection import _factory_params`
- **THEN** the import succeeds and the symbol resolves to the parameter-introspection function

#### Scenario: container.py stays under SLOC budget without suppression

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/packages/di/container.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

### Requirement: list-verb decoration helpers SHALL live in their own module

The list-verb decoration-time validators SHALL live in `src/a2kit/_list_helpers.py`, exporting `check_list_return_annotation` and `derive_selectable_fields`.

#### Scenario: List helpers importable from the sibling module

- **WHEN** consumer code or tests do `from a2kit._list_helpers import derive_selectable_fields`
- **THEN** the import succeeds and the symbol resolves to the fields-derivation function

#### Scenario: tool.py verb decorators stay in tool.py

- **WHEN** consumer code imports `from a2kit.tool import read, write, list_`
- **THEN** the imports succeed and the verb decorators remain on `tool.py` (the future `_verbs.py` split is out of scope for this change)
