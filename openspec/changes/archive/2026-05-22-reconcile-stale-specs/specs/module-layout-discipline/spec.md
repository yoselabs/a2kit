## ADDED Requirements

### Requirement: Underscore-prefixed modules are confined to an allowlisted set of private siblings

A Python file in `src/a2kit/` with a leading-underscore filename (e.g. `_foo.py`) SHALL exist only as an allowlisted private sibling of a public module — a deliberate code-split that keeps the public file under the SLOC budget. The allowlist is enforced by `src/a2kit/packages/lint/rules/mirror.py` and currently includes `_lifecycle_helpers.py`, `_list_helpers.py`, `_verbs.py`, `_verb_validators.py`, and `packages/di/_introspection.py`. An underscore-prefixed module that is NOT on this allowlist SHALL be flagged by the mirror lint rule. Symbols re-exported from a private sibling SHALL be re-exported through its public counterpart so external code imports the public name.

This requirement supersedes the earlier blanket prohibition on underscore-prefixed modules: that prohibition contradicted later requirements in this same capability that REQUIRE `_verbs.py` and `_verb_validators.py` to exist. The reconciled rule is "underscore modules are allowed only as allowlisted private siblings," which the code's mirror rule already enforces.

#### Scenario: Allowlisted private sibling is permitted

- **WHEN** `uv run a2kit lint static src/` runs against a tree containing `src/a2kit/_verbs.py`
- **THEN** no mirror-rule diagnostic is emitted for `_verbs.py` (it is on the ALLOW_LIST)

#### Scenario: Non-allowlisted underscore module is flagged

- **WHEN** `uv run a2kit lint static src/` runs against a tree containing a new `src/a2kit/_scratch.py` not on the ALLOW_LIST
- **THEN** the mirror lint rule reports `_scratch.py`

#### Scenario: Public symbols are re-exported through public files

- **WHEN** external code imports a verb decorator
- **THEN** it imports `from a2kit.tool import read` (a public module), even though the decoration body lives in the private sibling `_verbs.py`

## MODIFIED Requirements

### Requirement: One concept per file, name equals concept

Every file in `src/a2kit/` SHALL answer "what is this?" by its filename alone, without requiring a docstring or comment to explain the file's existence. Filenames SHALL name a single concept rather than a slice of one.

#### Scenario: File names are self-evident

- **WHEN** a reader scans `ls src/a2kit/` and `ls src/a2kit/<subpackage>/`
- **THEN** every filename maps to a single, namable concept (e.g. `tool.py`, `routers.py`, `app.py`) — not a slice of one (e.g. `_decorator_impl.py`, `_decorator_helpers.py`)

#### Scenario: No "helper" or "utils" modules

- **WHEN** the source tree is inspected
- **THEN** no module is named `helpers.py`, `utils.py`, `common.py`, `_utils.py`, or `_common.py` (the allowlisted `_lifecycle_helpers.py` and `_list_helpers.py` are named for their concept — verb-lifecycle and list-verb decoration — not as generic "helpers" buckets)

## REMOVED Requirements

### Requirement: No underscore-prefixed modules with public symbols

**Reason**: This requirement asserted that `src/a2kit/` contains zero underscore-prefixed modules (one scenario: `find src/a2kit -type f -name "_*.py" ... is empty`). It directly contradicts later requirements in the same capability that REQUIRE `_verbs.py`, `_verb_validators.py`, `_list_helpers.py`, and `packages/di/_introspection.py` to exist as private siblings. The code keeps these private siblings deliberately (mirror-rule ALLOW_LIST) to stay under the SLOC budget. The contradiction is resolved by the MODIFIED "Underscore-prefixed modules are confined to an allowlisted set of private siblings" requirement.

**Migration**: Underscore-prefixed modules are permitted when allowlisted in `packages/lint/rules/mirror.py`. Do not expect `find src/a2kit -name "_*.py"` to be empty.

### Requirement: `_APP_CTX` lives in `packages/cli/app_ctx`

**Reason**: This requirement mandates that `_APP_CTX: ContextVar` be defined in `src/a2kit/packages/cli/app_ctx.py`. No such file exists. The named module `a2kit.packages.cli.app_ctx` is a phantom; the requirement's scenarios (`_APP_CTX is defined exactly once, in src/a2kit/packages/cli/app_ctx.py`) cannot be satisfied. The active-`App` propagation mechanism, wherever it lives, is not at the path this requirement names, and no current capability depends on the `app_ctx.py` location.

**Migration**: There is no `packages/cli/app_ctx.py`. Code that needs the active-`App` propagation seam should consult the actual `packages/cli/` module layout. A reconciled CLI-internals spec, if needed, is a follow-up.
