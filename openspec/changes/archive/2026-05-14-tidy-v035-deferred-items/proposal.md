## Why

Four addressable items remain after the v0.35 lifecycle wave. None blocks
the release, but each is a known soft spot the next agent will trip on:
the verb-decorator SLOC overhang in `tool.py`, an unimplemented
spec requirement for topological singleton entry, an unenforced ty-gate
on `tests/`, and one stale "skipped until implementation lands" docstring
that no longer describes reality. Closing them now keeps the framework
discipline (no noqa, no skipped tests, no stale comments) honest.

Out of scope for this change:
- a2web consumer migration (lives outside this repo)
- CHANGELOG version cut / pyproject bump (pure release op, handled at
  tag time without an OpenSpec proposal)

## What Changes

- Extract `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` decorator
  bodies from `src/a2kit/tool.py` into a new private
  `src/a2kit/_verbs.py`. `tool.py` keeps the public re-exports
  (`read`, `write`, `list_`); decoration internals move. Drop the
  `# noqa: A2K014` from `tool.py`.
- Implement topological-order singleton entry in `App.__aenter__`
  using `Container._collect_reachable` so dependencies enter before
  dependents regardless of registration order. Un-skip
  `tests/test_lifecycle_topology.py::test_dependent_enters_after_dependency`.
- Tighten the `make lint` gate so `ty check tests/` is zero-tolerance
  (currently src/ is gated, tests/ has a 61-diagnostic baseline).
  Resolve every diagnostic; do not add `# type: ignore` to mask them
  unless the underlying type stub is the issue.
- Cosmetic: drop the stale "skipped at the module level until the
  implementation lands" docstring header in
  `tests/test_app_async_cm.py` (the implementation landed in v0.35).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `module-layout-discipline`: scope the verb-decorator extraction
  in. The `split-oversized-core-files` archive explicitly deferred
  `tool.py`; this change closes that deferral and makes `tool.py`
  noqa-free.
- `app-lifecycle`: tighten singleton-entry order from "registration
  order" to "topological order with registration-order as the
  tiebreaker for unrelated singletons". Removes the in-tree skip
  marker covering this requirement.
- `type-correctness-gate`: extend zero-tolerance from `src/` to
  `tests/`. Lint enforcement, not framework runtime behaviour.

## Impact

- `src/a2kit/tool.py` → shrinks to <500 SLOC; loses `# noqa: A2K014`.
- `src/a2kit/_verbs.py` → NEW; private module hosting verb decorator
  bodies + their helpers.
- `src/a2kit/packages/lint/rules/mirror.py` → add `_verbs.py` to the
  ALLOW_LIST (sibling private helper, same pattern as
  `_lifecycle_helpers.py` / `_list_helpers.py`).
- `src/a2kit/app.py` → `__aenter__` calls a topo-sorted view of
  `Container._collect_reachable` before entering.
- `tests/test_lifecycle_topology.py` → skip marker dropped.
- `tests/test_app_async_cm.py` → stale docstring header rewritten.
- `Makefile` → `make lint` runs `ty check tests/` and fails on any
  diagnostic.
- `tests/*` → ~61 small edits to clear ty diagnostics.
- No public-surface changes. No CHANGELOG migration entry needed
  (consumer-invisible).
