## 1. Generator

- [x] 1.1 Write a failing test for `scripts/component_map.py`: given the live layer manifest, the generator emits a markdown document listing every manifest unit with its layer, dependencies, and fan-in / fan-out.
- [x] 1.2 Implement `scripts/component_map.py`: import the assignment from `a2kit.packages.lint.layers`, parse the `src/a2kit/` import graph, render the unit table and the layer-ordered DAG.
- [x] 1.3 Generate the initial `docs/COMPONENT_MAP.md`.

## 2. Build integration

- [x] 2.1 Add a `component-map` target to the `Makefile`.
- [x] 2.2 Add a pre-commit hook in `.pre-commit-config.yaml` that regenerates the map and fails on staleness, modelled on the existing `adr-index` hook.
- [x] 2.3 Write a failing test asserting the committed `docs/COMPONENT_MAP.md` matches fresh generator output (the staleness gate).

## 3. Verification

- [x] 3.1 All tests from groups 1 and 2 pass.
- [x] 3.2 `make component-map` is idempotent — a second run produces no diff.
- [x] 3.3 `openspec validate --changes --strict` passes; the change is archive-ready.
