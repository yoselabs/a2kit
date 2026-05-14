## Context

Three of the four items in this change are bounded toil; the fourth
(topological singleton entry) is the only one with real algorithmic
substance. Bundling them is justified by their common shape — each is
a known soft spot tracked by a different artifact (noqa marker, skip
decorator, baseline tolerance, stale docstring) and each cleanup
removes that artifact. Splitting into four proposals would burn more
process than the work itself.

## Goals / Non-Goals

**Goals:**
- `src/a2kit/tool.py` ships without `# noqa: A2K014`.
- `tests/test_lifecycle_topology.py::test_dependent_enters_after_dependency`
  passes without `@pytest.mark.skip`.
- `make lint` invokes `uv run ty check tests/` and exits non-zero on
  any diagnostic; the current 61-diagnostic baseline goes to zero.
- The `tests/test_app_async_cm.py` module docstring no longer claims
  the tests are skipped.

**Non-Goals:**
- Public surface changes. Consumers see no API delta.
- CHANGELOG migration table entry (consumer-invisible cleanup).
- pyproject version bump / release cut.
- a2web migration.
- Touching `tests/test_transport_parity_stdio.py` (its skip is
  environmental, not a deferred item).

## Decisions

### 1. `_verbs.py` is a private sibling of `tool.py`

`tool.py` keeps the public re-exports (`read`, `write`, `list_`) so
consumer imports stay stable. The decorator implementations move to
`src/a2kit/_verbs.py`. The pattern mirrors the existing
`_lifecycle_helpers.py`, `_list_helpers.py`, and
`packages/di/_introspection.py` extractions.

**Why not a public `a2kit.verbs` module?** The decorators are the
public surface, not their internals. The underscore prefix tells
consumers "don't import from here directly". `tool.py` is the import
surface; `_verbs.py` is the host module.

**Mirror-rule update:** `src/a2kit/packages/lint/rules/mirror.py`'s
ALLOW_LIST already permits `_lifecycle_helpers.py`, `_list_helpers.py`.
Add `_verbs.py` to the same list.

### 2. Topological order via `Container._collect_reachable` + Kahn's algorithm

Currently `App.__aenter__` iterates `self._singletons` in registration
order. The container already has DI-graph traversal in
`_collect_reachable`. The fix is: build a sub-DAG of registered
singletons, topo-sort it, and enter in that order. Use registration
order as the tiebreaker between unrelated nodes so deterministic
ordering is preserved.

**Algorithm:**
1. Collect the set of registered singleton types.
2. For each, compute its DI-graph in-edges restricted to the
   registered set (via `_collect_reachable` or equivalent).
3. Kahn's algorithm with a stable tiebreaker (registration index)
   produces a deterministic topological order.
4. Enter in that order through the AsyncExitStack.

**Cycle handling:** the container already rejects cycles at
registration time, so `__aenter__` doesn't need a cycle check.

### 3. tests/ ty sweep is bulk-mechanical, not invasive

The 61 diagnostics fall into a few categories: missing return
annotations, narrow-typed stubs, untyped pytest fixtures. The sweep
should not introduce `# ty: ignore` in tests/ — the type-correctness
spec keeps the ≤10 budget in `src/` only, and tests/ should resolve
all diagnostics on the merit of the underlying type. Where a stub is
genuinely broken (e.g. `functools.wraps` `_Wrapped`), prefer a typed
re-binding over an ignore.

### 4. Makefile gate placement

Add `uv run ty check tests/` to the same `lint` target. Keep the
`src/` invocation distinct so a future split (e.g. ty profiles) is
easy. Both must exit zero for `make lint` to pass.

## Risks / Trade-offs

- **`_verbs.py` extraction risks subtle import cycles** → mitigation:
  `_verbs.py` must not import from `tool.py`; `tool.py` imports from
  `_verbs.py`. Same direction as `_list_helpers.py`.
- **Topological sort hides bugs in registration order** → not a
  practical risk; the spec already says topo order is canonical, and
  the skipped test pins the behaviour. If a consumer was depending on
  registration order, that was always a bug.
- **tests/ ty sweep churn** → keep diffs focused; do not refactor
  tests opportunistically.
- **Mirror-rule oversight** → covered by the existing
  `module-layout-discipline` spec; `_verbs.py` is added to the
  ALLOW_LIST in the same commit as the extraction.

## Migration Plan

Single PR (merged direct to `main`, per `feedback_no_prs`):

1. `_verbs.py` extraction + mirror-rule update + `tool.py` noqa drop.
2. Topological-entry implementation + un-skip the topology test.
3. tests/ ty sweep, file-by-file commits if large.
4. Makefile gate addition.
5. Docstring cleanup in `test_app_async_cm.py`.

No rollback needed; all changes are local refactors with green test
coverage.
