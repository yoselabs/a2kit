## 0. Prerequisites

- [ ] 0.1 Confirm `v1-cleanup-debt` change is applied (or its work merged) — this change builds on the v1.0 + cleanup baseline.
- [ ] 0.2 Confirm baseline: `uv run pytest -q --no-cov` → 252 passed; `uv run ty check src/` → All checks passed; `make lint` → 0; `uv run ruff check .` → 0.
- [ ] 0.3 Capture current test count (`find tests -name "test_*.py" | wc -l` and the pytest collected count) into the proposal as the "before" number.
- [ ] 0.4 Capture current line coverage (`uv run pytest --cov --cov-report=term --no-cov-on-fail | tail -2`) as the "before" number.

## 1. Tooling — install + configure mutmut

- [ ] 1.1 Add `"mutmut>=2.5"` to `pyproject.toml [dependency-groups] dev`. Run `uv sync --all-extras --dev`.
- [ ] 1.2 Add a `[tool.mutmut]` table to `pyproject.toml` with `paths_to_mutate`, `tests_dir`, `runner`, `simple_output`, `swallow_output`, `backup`, and an `exclude` list — each excluded file with a `# why:` rationale.
- [ ] 1.3 Add `.mutmut-cache/`, `html/`, and `mutants/` to `.gitignore`.
- [ ] 1.4 Add Make targets: `mutate`, `mutate-fast`, `mutate-show`, `mutate-html`, `mutate-baseline` per design.md D-MAKE-TARGETS.
- [ ] 1.5 Run `make mutate` once locally; capture the **baseline** aggregate score to `docs/MUTATION_BASELINE.md` (or commit message). This is the "before" number we measure against.

## 2. Mirror discipline — A2K-TEST-MIRROR rule

- [ ] 2.1 Create `src/a2kit/packages/lint/rules/mirror.py` implementing the A2K-TEST-MIRROR detector.
- [ ] 2.2 Define an explicit allow-list at the top of `mirror.py`: `__init__.py`, `__main__.py`, `runtime.py` (Protocol), `metadata.py` (frozen dataclass). Each entry has a `# why:` comment.
- [ ] 2.3 Implement source → test mirror path resolution per design.md D-MIRROR-FORMULA.
- [ ] 2.4 The rule fires when a non-exempt source file has no mirror OR the mirror exists but contains no `def test_*` function.
- [ ] 2.5 Wire the rule into `static.py`'s `RULES` dispatch tuple.
- [ ] 2.6 Catalog test-only files: create `tests/_test_only.txt` listing `conftest.py`, `test_cold_start.py`, `test_type_correctness_gate.py`, etc. The lint rule reads this list and skips those files.
- [ ] 2.7 Add tests in `tests/packages/lint/rules/test_mirror.py` covering: missing-mirror fires; empty-mirror fires; allow-listed files don't fire; test-only manifest entries don't fire.

## 3. Mirror sweep — fill the structural gaps

- [ ] 3.1 Run the new rule against the current tree. Capture the list of missing mirrors as `MIRROR_GAPS.md` (working doc; deleted at end of phase).
- [ ] 3.2 For each missing mirror, follow design.md D-MIRROR-SPLIT-VS-MERGE: split if the per-file test would be ≥ 30 LOC; otherwise create a stub mirror that re-exports tests from the consolidated location.
- [ ] 3.3 Specifically split `tests/packages/lint/test_di_rules.py` (21 tests, 5 rule families) into:
  - `tests/packages/lint/rules/test_di.py`
  - `tests/packages/lint/rules/test_conn.py`
  - `tests/packages/lint/rules/test_importing.py`
  - `tests/packages/lint/rules/test_shape.py`
  - `tests/packages/lint/rules/test_budget.py`
- [ ] 3.4 Create `tests/packages/lint/rules/__init__.py` and any other missing `__init__.py` files.
- [ ] 3.5 Verify `uv run a2kit lint static src/ tests/` — A2K-TEST-MIRROR fires zero findings.
- [ ] 3.6 Verify `uv run pytest -q --no-cov` — full suite passes (no test count regression).
- [ ] 3.7 Delete `MIRROR_GAPS.md`.

## 4. Mutation-driven test additions

- [ ] 4.1 Run `make mutate` (full). Save the per-file survival report as input.
- [ ] 4.2 For each source file with mutation score < 80 %: run `make mutate-show` filtered to that file; review survived mutations; add focused tests to kill them.
- [ ] 4.3 Priority targets (from v1-cleanup-debt depth gap):
  - `mcp/listview.py` (was 36 % line cov; mutation score expected lower) — add e2e MCP roundtrip via `await server._mcp_call_tool(...)`.
  - `lint/rules/*` AST walkers — add positive + negative AST fixtures per rule.
  - `cli/builder.py` `_make_tool_command` — exercise rare option-synthesis branches.
- [ ] 4.4 Re-run `make mutate` after each batch of additions. Confirm aggregate score is increasing.
- [ ] 4.5 Stop when aggregate score ≥ 90 % AND every per-file score is ≥ 80 % OR documented as exempt in `[tool.mutmut].exclude`.

## 5. Test consolidation

- [ ] 5.1 Run `mutmut` against the current suite. For tests that contribute zero mutation-killing power, mark them as candidates for deletion (write to a `TEST_DUPLICATES.md` working doc).
- [ ] 5.2 For each candidate: confirm by removing the test temporarily and re-running `mutmut`. If mutation score is unchanged, the test is redundant. Delete it.
- [ ] 5.3 Apply parametrize where 4+ near-identical tests exist (e.g., `Optional[int]` / `Optional[float]` / `Optional[str]` / `Optional[bool]` in `test_builder.py` could collapse to one parametrized test).
- [ ] 5.4 Verify `uv run pytest -q --no-cov` still green and `mutmut` aggregate score has not dropped.
- [ ] 5.5 Acceptance: post-cleanup test count ≤ baseline AND aggregate mutation score ≥ baseline + 5 percentage points.
- [ ] 5.6 Delete `TEST_DUPLICATES.md`.

## 6. CI integration

- [ ] 6.1 Add a GitHub Actions (or equivalent) workflow `.github/workflows/mutmut-pr.yml` that runs `make mutate-fast` on every PR; soft-fails (warning) if survived mutations on changed files; hard-fails if mutation score on changed files < 80 %.
- [ ] 6.2 Add a nightly workflow `.github/workflows/mutmut-nightly.yml` that runs `make mutate` on `main`; hard-fails if aggregate < 90 %; updates a status badge artifact.
- [ ] 6.3 README badge: add a "mutation score" badge to the top of `README.md` reflecting the latest nightly aggregate.
- [ ] 6.4 Document the workflow in a new `docs/MUTATION_TESTING.md` (link from README).

## 7. Documentation

- [ ] 7.1 Add a "Test Quality" section to `README.md` explaining mutation testing, the mirror rule, and how contributors should respond to A2K-TEST-MIRROR findings.
- [ ] 7.2 Add a workflow note to `ANTIPATTERNS.md`: "100 % line coverage does not imply tests catch bugs. mutmut is the validation."
- [ ] 7.3 Update `CHANGELOG.md` (next-version section, since v1.0 is shipped) with the mutation-testing rollout notes.
- [ ] 7.4 Update the `simplify-and-thin-core` Phase-7 Task 7.10 status comment to point at this change as the resolution path.

## 8. Verification

- [ ] 8.1 `uv run a2kit lint static src/ tests/` — A2K-TEST-MIRROR fires zero findings.
- [ ] 8.2 `uv run pytest -q --no-cov` — full suite passes; test count ≤ baseline.
- [ ] 8.3 `make mutate` aggregate score ≥ 90 %.
- [ ] 8.4 Per-file mutation scores: every file is ≥ 80 % OR explicitly excluded with rationale.
- [ ] 8.5 README badge reflects the actual nightly aggregate.
- [ ] 8.6 `make lint` exits 0 (includes A2K-TEST-MIRROR).
- [ ] 8.7 First-time-reader smoke: `tree tests/ src/a2kit/` shows clean 1:1 mirror; ratio of source files (excluding exemptions) to test files is exactly 1:1.

## 9. Tag readiness — when the next change ships

- [ ] 9.1 Update `docs/MUTATION_BASELINE.md` with final scores (per-file + aggregate).
- [ ] 9.2 Pause for explicit user authorization before merging.
