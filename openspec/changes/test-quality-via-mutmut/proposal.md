## Why

Coverage in v1.0 is **77 %** and the spec target is ≥ 95 %. The naive
fix is "write more tests" — but pure line/branch coverage rewards
volume over signal. Three concrete pathologies the v1.0 suites exhibit:

1. **Subagent test sprawl**: each Phase-2 / Phase-3 subagent wrote tests
   in isolation. Some files duplicate fixtures, others test the same
   path twice from different angles. **252 tests** is generous for
   ~2.7 K LOC; mutation testing will surface the redundant ones.
2. **Coverage that doesn't catch mutations**: `lint/static.py` was
   77 %-covered and *still* shipped a `_parse_select_atoms_cel` stub
   that returned `None` and was never exercised. Mutation testing
   would have caught that.
3. **Mirror drift**: `tests/` is supposed to mirror `src/a2kit/` per
   spec `module-layout-discipline / Test directory mirrors source
   structure`. Currently 32 test files for 42 source files; some
   plugin packages have rich tests, others have stubs. The mirror is
   *aspirational*, not enforced.

`mutmut` (Astral-friendly mutation testing for Python) is the right
tool: it injects faults into the source and measures whether the test
suite catches them. The result is a **mutation score** per file plus
a list of survived mutations — concrete, actionable signal that line
coverage cannot give.

This change pays the "tests must catch the bugs they exist to catch"
debt. Output: enforce mirror structure, kill duplicate / weak tests,
add focused tests for survived mutations, and gate the mutation score
in CI.

## What Changes

### Tooling

- Add `mutmut>=2.5` to `[dependency-groups] dev`.
- Add `[tool.mutmut]` config to `pyproject.toml`: paths, runner,
  baseline test command, exclusion list (third-party stubs, generated
  code).
- New `make` targets: `make mutate` (full run), `make mutate-fast`
  (only files changed since `main`), `make mutate-show` (dump
  survived mutations).
- CI job: `mutmut` runs nightly on `main`; PRs run mutation testing
  only on changed files via `make mutate-fast`.

### Test mirror discipline

- For every `src/a2kit/<path>/<file>.py` (excluding `__init__.py` and
  `__main__.py`), there SHALL be a corresponding
  `tests/<same path>/test_<file>.py`. Missing test files are a lint
  failure (new rule **A2K-TEST-MIRROR**).
- Stub test files are fine — they document the gap. Empty test files
  aren't allowed; each must have at least one `test_*` function.

### Test quality discipline

- Establish a **mutation score floor**: ≥ 80 % per file, ≥ 90 %
  aggregate. The aggregate floor is gated in CI; per-file floor is
  advisory (some files like `runtime.py` Protocols have no testable
  behavior).
- Mutation gaps surface in CI as actionable comments on PRs (which
  mutations survived, where).
- **Reduce test count where redundancy is documented.** Acceptance
  criterion: post-cleanup, total test count is `≤ current count`
  AND mutation score is `≥ before-cleanup score + 5 %`. Better
  signal with less code.

### Mirror sweep + new tests

- Audit every `src/a2kit/**/*.py` for a corresponding test file. Fill
  gaps. Where `mutmut` reports survived mutations, add focused tests
  to kill them.
- Specific gap targets (from coverage report):
  - `lint/rules/*` — most rule modules at 70-90 %; survived mutations
    likely on edge-case AST shapes. Mirror at `tests/packages/lint/rules/test_<rule>.py`.
  - `mcp/listview.py` (36 %) — middleware result-rewriting paths.
    Add e2e MCP roundtrip in `tests/packages/mcp/test_listview.py`.
  - `cli/builder.py` `_make_tool_command` complexity branches.

### Documentation

- Add a "Test Quality" section to `README.md` linking the mutation
  score badge and explaining the mirror rule.
- Add a workflow note in `ANTIPATTERNS.md`: "coverage = 100 % does not
  imply tests catch bugs; mutmut is the validation".

## Capabilities

### New Capabilities

- `mutation-test-quality`: enforces a mutation-score floor in CI
  (`mutmut`), `make mutate*` targets, exclusion config, and PR-time
  gating on changed files.
- `test-mirror-discipline`: every source file has a corresponding
  test file; missing test files are a lint failure
  (A2K-TEST-MIRROR); empty test files are forbidden.

### Modified Capabilities

- `module-layout-discipline`: tightens "Test directory mirrors source
  structure" — replaces the soft "should" with a hard lint rule and
  defines the mirror formula.
- `type-correctness-gate`: gain a sibling gate (mutation testing).
  Both are part of `make lint` / CI parity.

## Impact

- **Affected code**: `tests/**` (additions, consolidations, possible
  deletions of redundant tests), `src/a2kit/packages/lint/rules/`
  (new A2K-TEST-MIRROR rule), `pyproject.toml`, `Makefile`.
- **APIs**: no public surface changes.
- **Dependencies**: `mutmut` added to dev. ~5 MB install. Optional —
  skipping the dev group still lets users install/run a2kit; mutation
  testing only relevant for contributors and CI.
- **CI cost**: full mutation run on a 2.7 K-LOC codebase is ~5-10 min.
  PR-time `mutate-fast` runs only changed files, typically <1 min.
- **Deferred from `v1-cleanup-debt`**: tasks 3.1-3.6 (coverage uplift
  to 95 %) become inputs to *this* change. Mutation testing replaces
  the coverage-to-95 % aspiration as the quality bar.
- **Risk**: mutation testing can be flaky (timeouts on slow tests,
  mutations that compile but are runtime no-ops). Mitigation: per-file
  exclusion list; documented mutation-score floor allows for known
  unkillable mutations.
