## MODIFIED Requirements

### Requirement: Quality-gate parity in `make lint` and CI

`make lint` SHALL run **all four** quality gates:

1. `uv run ruff check .` (lint)
2. `uv run ruff format --check .` (format)
3. `uv run ty check src/` (type correctness)
4. `uv run a2kit lint static src/ tests/ examples/` (a2kit static rules,
   including A2K-TEST-MIRROR)

A new sibling gate — `make mutate` (mutation testing) — runs **outside**
`make lint` due to its runtime cost (~10 minutes). CI runs `make mutate`
nightly on `main` and `make mutate-fast` per PR.

#### Scenario: `make lint` runs all four static gates
- **WHEN** `make lint` is invoked in a clean checkout
- **THEN** ruff check, ruff format-check, ty check, and a2kit lint static
  all execute; the target exits 0 only when all four pass

#### Scenario: A2K-TEST-MIRROR is part of `make lint`
- **WHEN** `make lint` runs against a tree where a source file lacks
  its mirror
- **THEN** the `a2kit lint static` invocation fails with an
  A2K-TEST-MIRROR finding; `make lint` exits non-zero

#### Scenario: Mutation testing is a separate Make target
- **WHEN** `make lint` is invoked
- **THEN** mutation testing does NOT run; `make mutate` is the
  dedicated entry point

#### Scenario: Aggregate-score floor is CI-enforced
- **WHEN** the nightly CI workflow runs `make mutate` on `main`
- **THEN** the workflow exits non-zero if the aggregate mutation
  score reported by `mutmut results` falls below 90 %
