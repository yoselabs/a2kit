## ADDED Requirements

### Requirement: `A2K-CORE-PURITY` rule forbids package imports from core

A new static lint rule `A2K-CORE-PURITY` SHALL fire when any file
under `src/a2kit/` (excluding `src/a2kit/packages/**`) imports from
`a2kit.packages.*`. The rule SHALL be enabled by default and run as
part of `make lint`.

The allowlist of permitted core files is documented in the rule:

- `src/a2kit/__init__.py`
- `src/a2kit/__main__.py`
- `src/a2kit/app.py`
- `src/a2kit/capabilities.py`
- `src/a2kit/exceptions.py`
- `src/a2kit/metadata.py`
- `src/a2kit/plugin.py` (new)
- `src/a2kit/routers.py`
- `src/a2kit/runtime.py`
- `src/a2kit/signature.py`
- `src/a2kit/store.py` (DELETED by this change)
- `src/a2kit/tool.py`

Files in `src/a2kit/packages/**` are NOT subject to this rule (they
ARE the packages; they may import from each other or from core).

#### Scenario: Core file imports from package — fires
- **WHEN** `src/a2kit/app.py` contains `from a2kit.packages.connections import ConnectionConfig`
- **THEN** the rule emits one finding with code `A2K-CORE-PURITY`

#### Scenario: Package file imports from another package — silent
- **WHEN** `src/a2kit/packages/mcp/server.py` contains `from a2kit.packages.enrichers import wrap`
- **THEN** the rule does not fire

#### Scenario: Package file imports from core — silent
- **WHEN** `src/a2kit/packages/connections/plugin.py` contains `from a2kit.metadata import A2KitMeta`
- **THEN** the rule does not fire

#### Scenario: Indirect import via re-export still fires
- **WHEN** `src/a2kit/app.py` contains `import a2kit.packages.connections` (whole module)
- **THEN** the rule fires
