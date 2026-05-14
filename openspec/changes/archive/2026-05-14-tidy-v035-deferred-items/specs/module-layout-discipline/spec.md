## MODIFIED Requirements

### Requirement: list-verb decoration helpers SHALL live in their own module

The list-verb decoration-time validators SHALL live in `src/a2kit/_list_helpers.py`, exporting `check_list_return_annotation` and `derive_selectable_fields`. The verb decorators themselves (`read`, `write`, `list_`) SHALL be re-exported from `a2kit.tool` but their decoration-time bodies SHALL live in `src/a2kit/_verbs.py`. `tool.py` SHALL NOT carry a `# noqa: A2K014` suppression after the verb extraction lands.

#### Scenario: List helpers importable from the sibling module

- **WHEN** consumer code or tests do `from a2kit._list_helpers import derive_selectable_fields`
- **THEN** the import succeeds and the symbol resolves to the fields-derivation function

#### Scenario: Verb decorators importable from `a2kit.tool`

- **WHEN** consumer code imports `from a2kit.tool import read, write, list_`
- **THEN** the imports succeed and the decorators behave identically to pre-extraction

#### Scenario: Verb decoration bodies live in `_verbs.py`

- **WHEN** `from a2kit._verbs import read, write, list_` is executed
- **THEN** the import succeeds and `a2kit.tool.read is a2kit._verbs.read` (same object, re-exported)

#### Scenario: tool.py is noqa-free under the A2K014 budget

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/tool.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

## ADDED Requirements

### Requirement: Mirror-rule ALLOW_LIST SHALL permit `_verbs.py`

`src/a2kit/packages/lint/rules/mirror.py` SHALL list `_verbs.py` in its ALLOW_LIST of private sibling modules permitted to coexist with their public counterparts, alongside `_lifecycle_helpers.py`, `_list_helpers.py`, and `packages/di/_introspection.py`.

#### Scenario: Mirror rule allows `_verbs.py`

- **WHEN** `uv run a2kit lint static src/` runs against the source tree containing `src/a2kit/_verbs.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verbs.py`
