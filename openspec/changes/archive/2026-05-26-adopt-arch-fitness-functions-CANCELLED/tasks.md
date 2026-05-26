## 1. BDD specs (write tests first)

- [ ] 1.1 Capability test `tests/capabilities/arch_fitness_functions/test_archon_rules_collected.py` — pytest collects every file under `tests/architecture/` and the suite runs as part of `pytest`.
- [ ] 1.2 Capability test `tests/capabilities/arch_fitness_functions/test_make_arch_target.py` — `make arch` invokes the pytest-archon test set and exits 0 on a clean tree.

## 2. pytest-archon bootstrap

- [ ] 2.1 Add `pytest-archon` to `dev` deps in `pyproject.toml`.
- [ ] 2.2 Create `tests/architecture/__init__.py` and `tests/architecture/conftest.py` (the conftest may be empty; it exists to anchor the directory as a pytest package).

## 3. Rules

- [ ] 3.1 Write `tests/architecture/test_packages_init_is_only_public_surface.py` — walk every `src/a2kit/packages/<name>/__init__.py`, parse the AST, fail if any `_`-prefixed name appears in `__all__` or in a `from ._x import _name` re-export.
- [ ] 3.2 Write `tests/architecture/test_tool_returns_are_pydantic.py` — walk every `@tool` / verb-decorated function in `src/a2kit/` and `examples/`, fail when the return annotation resolves to `str` / `dict` / a non-pydantic structural type. Reuse the `tool-return-type-discipline` spec's scenarios as test fixtures.
- [ ] 3.3 Write `tests/architecture/test_no_dict_str_any_on_internal_dataclasses.py` — walk every `@dataclass` / frozen-dataclass / pydantic model under `src/a2kit/packages/`, fail when a field's annotation is `dict[str, Any]` UNLESS the field is allowlisted (allowlist lives in the test module with one-line reason per entry).

## 4. Wiring

- [ ] 4.1 Add `arch:` target to `Makefile`: `uv run pytest tests/architecture -q`.
- [ ] 4.2 Make `make lint` depend on `make arch` (or add `arch` to the umbrella check target — match the existing convention).
- [ ] 4.3 CI: ensure `make lint` (or its replacement) is the required gate; nothing extra needed if `arch` is wired into it.

## 5. Docs

- [ ] 5.1 New `docs/patterns/arch-fitness-functions.md` (or extend an existing structural doc) — short narrative: what archon enforces, when to add a new rule, why no Tach.
- [ ] 5.2 Update `AGENTS.md` (and `CLAUDE.md` overlay if duplicated): point at `make arch` as the structural rule harness; flag that one-off rules belong under `tests/architecture/`, not in scattered `tests/test_*.py`.
- [ ] 5.3 `CHANGELOG.md` `[Unreleased]` entry — short paragraph; flag no behaviour change.

## 6. Verification

- [ ] 6.1 `make arch` green on a clean tree.
- [ ] 6.2 `make lint` (or equivalent) invokes `make arch` and exits 0.
- [ ] 6.3 Deliberately add a `_internal` re-export to a package `__init__.py` → archon red. Revert.
- [ ] 6.4 Deliberately change a `@tool` return annotation to `str` → archon red. Revert.
- [ ] 6.5 Deliberately add a `dict[str, Any]` field to an internal dataclass NOT on the allowlist → archon red. Revert.

## 7. Open questions to resolve during implementation

- [ ] 7.1 Should the allowlist for `dict[str, Any]` (rule 3.3) live in the test module (data adjacent to rule) or in a separate `tests/architecture/allowlist.toml`? Default: in the test module. Revisit if the list grows past ~10 entries.
- [ ] 7.2 Should the `@tool` discovery in rule 3.2 read from `ToolDescriptor` (runtime introspection) or from AST decorator names (static)? AST is more honest (catches "you decorated it but never registered"); ToolDescriptor matches what actually runs. Default: AST, with a follow-up to add a runtime-introspection rule if AST misses load-bearing cases.
