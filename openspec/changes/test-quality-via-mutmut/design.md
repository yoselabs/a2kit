## Context

After the v1.0 thin-core refactor (`simplify-and-thin-core`) and the
follow-up `v1-cleanup-debt` change, the test suite stands at
**252 tests, 32 files, 77 % line coverage**. The numbers look fine on
paper, but the v1.0 work surfaced three concrete signals that the
suite is **wide but shallow**:

1. The retired A2K010 rule shipped a `_parse_select_atoms_cel` stub
   that always returned `None`. No test caught it because lines were
   "covered" — the function executed and returned. Mutation testing
   would have flagged it instantly: every mutation to the body was
   semantically equivalent to "return None unchanged", so all
   mutations would survive.
2. Phase-2 / Phase-3 subagents wrote tests in isolation. Manual audit
   of `tests/packages/cli/` shows 2-3 redundant top-level-help
   assertions; same for `tests/packages/lint/`. The suite optimised
   for "coverage of features" not "coverage of behavior".
3. The mirror rule from `module-layout-discipline` is documented but
   not enforced. 32 test files vs 42 source files. Some plugin
   packages (`enrichers/` — 1 file → 1 test file, well-mirrored)
   are clean. Others (`lint/rules/` — 6 modules → 1 monolithic
   test_di_rules.py + test_static.py + test_runtime.py — not
   mirrored) drifted as the source split.

`mutmut` is the standard Python mutation tester. It injects
"plausible" faults — flip operators, swap constants, drop returns —
runs the test suite, and tabulates per-mutation survival. The output
is a per-file mutation score and a list of survived mutations to
target.

**Reference example from this repo**: in v1.0 we shipped this stub:

```python
def _parse_select_atoms_cel(expr: str) -> list[tuple[str | None, str]] | None:
    return None
```

`mutmut` would generate mutations like:
- `return None` → `return []`  (would survive — no test calls it)
- `return None` → `return [("x", "y")]`  (would survive)
- `def _parse_select_atoms_cel(expr): pass`  (would survive)

100 % survival → 0 % mutation score on this function → **dead code
detected**. We caught this manually post-v1.0; mutmut would have
caught it pre-merge.

## Goals / Non-Goals

### Goals

- Mutation-test-score floor: **≥ 90 % aggregate** across `src/a2kit/`.
- Per-file mutation scores reported and tracked.
- `tests/` mirrors `src/a2kit/` exactly: one test file per source file
  (excluding `__init__.py` and `__main__.py`), enforced by lint rule
  **A2K-TEST-MIRROR**.
- Test count post-cleanup ≤ current count (252) AND mutation score
  ≥ baseline + 5 percentage points.
- `make mutate` runs locally (full, ~10 min) and in CI nightly.
- `make mutate-fast` runs in PRs in <1 min on changed files.
- README documents the workflow: "coverage is necessary but not
  sufficient; mutmut catches the bugs your tests don't".

### Non-Goals

- 100 % mutation score. Some mutations are equivalent (e.g. `if x: pass`
  → `if x: pass`-equivalent reorderings). Hard floor at 80 % per file
  acknowledges that.
- Replacing pytest. mutmut wraps pytest; the existing suite stays.
- Property-based testing rollout. Hypothesis is already a dev dep but
  introducing it as a discipline is a separate change.
- Performance regression testing. Coverage and mutation testing are
  about correctness; benchmark stability is its own discipline.
- Mutation testing on `examples/` or `tests/` themselves. Only
  `src/a2kit/` is the unit under test.

## Decisions

### D-MUTMUT-CONFIG: `[tool.mutmut]` in `pyproject.toml`

```toml
[tool.mutmut]
paths_to_mutate = ["src/a2kit/"]
tests_dir = "tests/"
runner = "uv run pytest -x --no-cov --import-mode=importlib"
exclude = [
    # Protocols and dataclasses have no testable behavior.
    "src/a2kit/runtime.py",       # ToolContext Protocol
    "src/a2kit/metadata.py",      # A2KitMeta dataclass
    # __init__ files are pure re-exports.
    "**/__init__.py",
    # __main__.py is one Click group definition with no mutable behavior.
    "src/a2kit/__main__.py",
]
backup = false
swallow_output = true
simple_output = true
```

`runner = "uv run pytest -x --no-cov --import-mode=importlib"`:

- `-x` — stop on first failure (mutmut needs only "did any test fail",
  not "all tests").
- `--no-cov` — coverage is a separate concern; running coverage on
  every mutation is wasteful.
- `--import-mode=importlib` — matches the project's pytest config
  (Phase 5 of `v1-cleanup-debt`).

### D-MIRROR-RULE: A2K-TEST-MIRROR lint rule

A new rule under `src/a2kit/packages/lint/rules/mirror.py`:

- For each `src/a2kit/<path>/<file>.py` (where `<file>.py` is not
  `__init__.py` or `__main__.py`): assert
  `tests/<path>/test_<file>.py` exists.
- For each test file: assert it contains at least one
  `def test_*` function.

Why a custom rule and not a pytest plugin: lint rules already ship
in the codebase, run in `make lint`, and produce machine-readable
output. A pytest collection-time check would only fire when running
the test suite — too late.

### D-MIRROR-FORMULA: deterministic test path

Source path → test path mapping:

```
src/a2kit/foo.py                        → tests/test_foo.py
src/a2kit/packages/cli/builder.py       → tests/packages/cli/test_builder.py
src/a2kit/packages/lint/rules/di.py     → tests/packages/lint/rules/test_di.py
```

Edge cases:

- `src/a2kit/__init__.py` and `src/a2kit/__main__.py` — exempted (no
  testable behavior).
- `src/a2kit/packages/__init__.py` — exempted (namespace).
- Source modules whose only purpose is type aliases (e.g.
  `runtime.py` if it stays pure-Protocol) — exempted via the
  `[tool.mutmut].exclude` list AND the lint rule's allow-list.

### D-MAKE-TARGETS

```makefile
mutate:
	uv run mutmut run

mutate-fast:
	# Only mutate files changed since main.
	uv run mutmut run --paths-to-mutate "$$(git diff --name-only origin/main... | grep '^src/a2kit/' | tr '\n' ',' | sed 's/,$$//')"

mutate-show:
	uv run mutmut show all

mutate-html:
	uv run mutmut html
	@echo "open html/index.html"

mutate-baseline:
	# Establish baseline mutation score for tracking; writes to .mutmut-baseline.json
	uv run mutmut run
	uv run mutmut results --json > .mutmut-baseline.json
```

The `make lint` target stays unchanged — mutation testing is too slow
to run on every lint invocation. CI runs the full mutmut nightly;
PRs run `mutate-fast`.

### D-CI-GATING

Two CI workflows:

1. **PR check**: `make mutate-fast`. Comment on PR with survived
   mutations on changed files. Soft-fail (warning) if any survive
   above the floor; hard-fail if mutation score on changed files
   drops below 80 %.
2. **Nightly main**: full `make mutate`. Update README badge with
   aggregate score. Hard-fail if aggregate drops below 90 %.

### D-TEST-CONSOLIDATION-RULES

When deduplicating, prefer:

- **One test per behavior**, not per code path. If two tests assert
  "tool A invocation works in CLI mode" via different routes, merge
  to the cleaner one.
- **Behaviour-named tests over implementation-named** —
  `test_optional_int_maps_to_integer_click_option` is good;
  `test_click_type_for_returns_int` is too implementation-tied.
- **Parametrize where shapes vary**, not where one test invocation
  per shape would be cleaner. Heuristic: 4+ near-identical tests →
  parametrize; 2-3 → keep separate.
- **Drop test code that doesn't kill mutations**. If a test contributes
  zero mutation-killing power (verified via `mutmut`), it's noise.

### D-MIRROR-SPLIT-VS-MERGE

When `tests/<dir>/test_<file>.py` doesn't exist but tests for that
file are scattered across siblings (e.g. `lint/rules/di.py` covered
by `tests/packages/lint/test_di_rules.py`):

- **Split** if the per-file test would be ≥ 30 LOC.
- **Keep current location + add a stub** `test_<file>.py`
  re-exporting the relevant tests if < 30 LOC. The stub satisfies
  A2K-TEST-MIRROR.

The `lint/rules/test_di_rules.py` situation: 21 tests covering 5 rule
families (di, conn, importing, shape, budget). Should split into
`test_di.py`, `test_conn.py`, etc. — clean mirror to source.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| `mutmut` flakiness (timeouts, equivalent mutations) | Per-file `exclude` list; mutation-score floor at 80 %, not 100 %; nightly run averages flakes out. |
| CI cost of nightly full run (10 min compute) | Acceptable; runs on `main` only, not PRs. PR cost is `mutate-fast` (<1 min). |
| Rewriting tests breaks the suite mid-flight | Land mirror restructuring first (no semantic changes); land mutation-driven additions second; consolidation last. Test count must stay green at every step. |
| A2K-TEST-MIRROR fires on legitimate exemptions | Rule's allow-list is explicit (Protocols, dataclasses, `__init__`); each entry has a `# why:` comment. |
| Test count "must not increase" creates pressure to skip useful tests | Acceptance criterion is `≤ current AND mutation score + 5 %`. If a *useful* new test pushes count up, that's fine — but the mutation-score uplift must justify it. |
| `mutmut` cache pollution between runs | `make mutate-baseline` resets; `.mutmut-cache/` in `.gitignore`. |
| Mutation testing surfaces real bugs that need fixing, not just test gaps | This is the *good* outcome; bugs found get fixed, tests added to lock the fix in. |

## Open questions (decide during implementation)

- Whether `mutmut` runs against the full suite or only `tests/packages/<n>/`
  for each source file. Lean: **full suite**. mutmut's `-tests-dir` flag
  scopes appropriately; per-file scoping is a v2 optimization.
- Whether to track the mutation-score baseline in git or in a CI artifact.
  Lean: **CI artifact** + a README badge. Avoids `.mutmut-baseline.json`
  churn in commits.
- Whether the A2K-TEST-MIRROR rule should also enforce the **inverse**
  (every test file has a source file). Lean: **no** — `tests/test_app.py`
  for `src/a2kit/app.py` is correct, but `tests/test_cold_start.py`,
  `tests/test_type_correctness_gate.py`, and `tests/conftest.py` are
  test-only modules with no source twin. Listing them as exemptions is
  cleaner.
- Test consolidation upper bound. Lean: target **≤ 220 tests** post-cleanup
  (down from 252) IF mutation score uplifts ≥ 5 %. If we can't uplift
  while shrinking, keep the current count.
