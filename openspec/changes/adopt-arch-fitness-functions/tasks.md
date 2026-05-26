## 1. BDD specs (write tests first)

- [ ] 1.1 Capability test `tests/capabilities/arch_fitness_functions/test_tach_check_runs.py` — running `tach check` on a clean tree exits 0; introducing a deliberate cross-package import causes exit non-zero.
- [ ] 1.2 Capability test `tests/capabilities/arch_fitness_functions/test_archon_rules_collected.py` — pytest collects every file under `tests/architecture/` and the suite runs as part of `pytest`.
- [ ] 1.3 Capability test `tests/capabilities/arch_fitness_functions/test_make_arch_target.py` — `make arch` invokes both Tach and the archon test set.

## 2. Tach bootstrap

- [ ] 2.1 Add `tach` to `dev` deps (pyproject) with version pin matching a2web's.
- [ ] 2.2 Write `tach.toml` at repo root, modelling every package under `src/a2kit/packages/*` with `depends_on = []` and the `a2kit` root declaring its allowed package dependency list.
- [ ] 2.3 Run `tach sync` once to capture today's violations as explicit exceptions in `tach.toml`. Annotate each with a comment block (`# GRANDFATHERED: <reason>. Retired by <ADR/BACKLOG item>.`) mirroring a2web's tach.toml convention.
- [ ] 2.4 Verify `tach check` exits 0 on the post-sync tree.

## 3. pytest-archon bootstrap

- [ ] 3.1 Add `pytest-archon` to `dev` deps.
- [ ] 3.2 Create `tests/architecture/__init__.py` and `conftest.py`.
- [ ] 3.3 Write `test_packages_init_is_only_public_surface` — no `_`-prefixed re-exports from any `packages/<name>/__init__.py`.
- [ ] 3.4 Write `test_tool_returns_are_pydantic` — capture the `tool-return-type-discipline` spec as an AST rule.
- [ ] 3.5 Write `test_no_dict_str_any_on_internal_dataclasses` — flag `dict[str, Any]` fields on `@dataclass` types inside `packages/`.

## 4. Retire hand-rolled tests

- [ ] 4.1 If `tests/test_packages_independence.py` exists, port any rule it covers that Tach doesn't (probably none) into archon, then delete the file.
- [ ] 4.2 Grep for other hand-rolled "no import from X" tests; replace or delete.

## 5. Wiring

- [ ] 5.1 Add `make arch` target (Makefile): `uvx tach check && uv run pytest tests/architecture -q`.
- [ ] 5.2 Wire `make arch` into `make lint` (or whatever the umbrella gate is).
- [ ] 5.3 Wire `make arch` into CI as a required step.

## 6. Docs

- [ ] 6.1 Update `AGENTS.md` (and `CLAUDE.md` overlay if it duplicates) to point at `make arch` as the structural-enforcement gate; remove any "Never import X" prose that now lives in `tach.toml`.
- [ ] 6.2 Add a short note in `docs/adr/` (or as an ADR) recording the Tach + pytest-archon decision, mirroring a2web ADR-0001's three-pattern reasoning trimmed to a2kit's scope.
- [ ] 6.3 Add a one-paragraph entry in `CHANGELOG.md` under `[Unreleased]` describing the structural gate (no public API change).

## 7. Verification

- [ ] 7.1 `make arch` green on a clean tree.
- [ ] 7.2 Deliberately introduce a cross-package import (e.g. `packages/cli` importing from `packages/mcp`) → `make arch` red. Revert.
- [ ] 7.3 Deliberately add a `_internal` re-export to a package `__init__.py` → archon red. Revert.
