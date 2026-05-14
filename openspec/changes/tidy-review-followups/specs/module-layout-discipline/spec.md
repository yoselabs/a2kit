## MODIFIED Requirements

### Requirement: Core source tree is at most 12 files

Core source SHALL contain at most 12 Python files at the top level of `src/a2kit/` (excluding `__init__.py`, `__main__.py`, and the `packages/` subtree).

#### Scenario: Core file count under threshold
- **WHEN** `find src/a2kit -maxdepth 1 -type f -name "*.py" -not -name "__init__.py" -not -name "__main__.py" | wc -l` is run
- **THEN** the result is ≤ 12

### Requirement: `_APP_CTX` lives in `packages/cli/app_ctx`

`_APP_CTX: ContextVar` SHALL be defined exactly once, in `a2kit.packages.cli.app_ctx`, and SHALL be used by `build_full_cli` and `serve_command` to propagate the active `App` across lazy subcommand dispatches. The previous Phase-3.1 location (`a2kit.packages.mcp.cli._APP_CTX`) is replaced; no compatibility re-export.

#### Scenario: Canonical location
- **WHEN** the source tree is inspected
- **THEN** `_APP_CTX` is defined exactly once, in
  `src/a2kit/packages/cli/app_ctx.py`

#### Scenario: mcp.cli imports from cli.app_ctx
- **WHEN** `src/a2kit/packages/mcp/cli.py` is read
- **THEN** it imports `_APP_CTX` from `a2kit.packages.cli.app_ctx`, not
  the reverse

## ADDED Requirements

### Requirement: Verb-decorator validators SHALL live in their own module

The return-annotation validators and reserved-name guards used by `@a2kit.read` / `@write` / `@list_` SHALL live in `src/a2kit/_verb_validators.py`, exporting `_check_return`, `_resolve_return_annotation`, `_check_reserved_name`, `_BUILTIN_RESERVED_TOOL_NAMES`, and `_RESERVED_TOOL_NAME_PREFIX`. `_verbs.py` SHALL re-export `_resolve_return_annotation` and the `_WARN_ONCE_RESOLVE_RETURN` set for test access.

#### Scenario: Validators importable from the sibling module

- **WHEN** consumer code does `from a2kit._verb_validators import _check_return, _resolve_return_annotation`
- **THEN** the imports succeed and the symbols resolve to the introspection functions

#### Scenario: `_verbs.py` stays under the SLOC budget

- **WHEN** `uv run a2kit lint static src/` runs against `src/a2kit/_verbs.py`
- **THEN** no `A2K014` diagnostic is emitted and the file carries no `# noqa: A2K014` suppression

#### Scenario: Mirror rule allows `_verb_validators.py`

- **WHEN** `uv run a2kit lint static src/` runs against the source tree containing `src/a2kit/_verb_validators.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verb_validators.py`
