## MODIFIED Requirements

### Requirement: Package private/public split is enforced by Tach

The `src/a2kit/packages/<name>/` private-by-default invariant — where `__init__.py` is the only public surface and every other submodule is private — SHALL be enforced by Tach via the `arch-fitness-functions` capability. The existing `__init__.py`-count formula in this spec remains as a documentation aid for human reviewers, but bypass of the boundary SHALL be a `tach check` failure, not a counting-test failure.

Hand-rolled enforcement tests (historically `tests/test_packages_independence.py`) SHALL be deleted when this requirement lands; their rule set is fully expressed by `tach.toml` plus the AST init-purity rule in `tests/architecture/`.

#### Scenario: Tach is the authoritative enforcer

- **WHEN** a contributor adds a cross-package import or imports `_`-prefixed names through a package front door
- **THEN** `make arch` exits non-zero via Tach (boundary) or pytest-archon (init purity)
- **AND** no separate counting-based test is required to catch the violation
