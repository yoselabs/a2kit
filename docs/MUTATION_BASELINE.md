# Mutation Baseline

> **Status (2026-05-09):** Baseline run blocked by mutmut 3.5 compatibility
> issues. Phases 4–5 of `test-quality-via-mutmut` are deferred until
> resolved. Phase 1 (tooling install + config) and Phase 2
> (A2K-TEST-MIRROR rule) ship independently.

## Configuration

mutmut 3.5 is installed, configured in `pyproject.toml [tool.mutmut]`,
and wired into `make` (targets `mutate`, `mutate-fast`, `mutate-show`,
`mutate-html`, `mutate-baseline`).

## Runs to date

| Run | Outcome |
|---|---|
| #1 | Failed at baseline collection: `tests/examples/` couldn't import `examples.streaming_logger`. **Fix**: added `also_copy = ["examples/"]` to mutmut config. |
| #2 | Failed at baseline collection: mutmut's trampoline injects `self` references but `connections/config.py` uses `__init_subclass__` (classmethod, takes `cls`). **Fix**: added `connections/config.py` to `do_not_mutate`. |
| #3 | Failed at baseline collection: `test_ty_ignore_count_under_budget` counted mutmut's injected `# ty: ignore` comments and breached the 10-budget. **Fix**: deselected that test + `test_import_a2kit_under_100ms_and_no_fastmcp` (cold-start budget under trampoline overhead). |
| #4 | Baseline collected. Mutation phase ran 4050 mutants. **All 4050 categorised as `segfault` (3823) or `no tests` (227); zero killed, zero survived.** |

## Diagnosis

The "segfault" category in mutmut means the pytest subprocess exited
with an unexpected status — neither a clean pass nor a normal test
failure. The pattern is uniform across files (every `__init__`,
`run`, `add_router`, etc. shows `segfault` for every mutant), which
suggests a systemic issue, not a per-file bug.

Likely root causes (need further investigation):

1. **Trampoline scaffolding incompatibility.** mutmut 3.x rewrites
   each function with a `_mutmut_trampoline` dispatcher. This pattern
   collides with several a2kit conventions: lazy imports inside
   functions, deferred fastmcp loading, `__getattr__` on
   `a2kit/__init__.py`, dataclass `__init_subclass__` hooks.
2. **Module-level side effects.** mutmut imports the mutated module
   during stat collection. a2kit's `__main__.py`, plugin packages
   with `connections_cli(...)` factories, and the cli `LazyGroup`
   may not survive trampoline injection cleanly.
3. **`pytest -x` early exit interpreted as segfault.** With `-x`,
   pytest stops on the first failing test. mutmut may classify
   this as a non-standard exit if internal pytest fixtures error
   out before the deselection takes effect.

## Path forward

This is a real upstream issue, not a config tweak. Three options:

1. **File a bug with mutmut and pin to a known-good prior version**
   (or wait for fix). Cosmic-ray is an alternative mutation tester.
2. **Manually exclude every file mutmut chokes on** until the
   surviving set produces meaningful output. Likely high noise.
3. **Defer mutation testing until a2kit's plugin architecture
   stabilises further.** Phase 2 (mirror discipline) ships now;
   mutation testing returns as a follow-up change.

Decision pending. For now, this file documents the blocker so
contributors can see why `make mutate` is configured but not gated
in CI.
