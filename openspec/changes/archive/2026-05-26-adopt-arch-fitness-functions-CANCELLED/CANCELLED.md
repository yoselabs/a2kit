# Cancelled — adopt-arch-fitness-functions

**Date:** 2026-05-26
**Reason:** Implementation revealed two design issues that shrank scope to the
point where a standalone OpenSpec change was overkill.

## What happened

1. **Tach dropped (first scope reduction).** A first-pass experiment with
   Tach 0.35.0 against a2kit's tree produced 40+ violations, but virtually
   all were model-mismatch false positives: Tach's flat dependency graph has
   no concept of foundational-core exempt modules
   (`FOUNDATIONAL_CORE_MODULES`), facade modules (`FACADE_MODULES`), or
   layer ordering — all of which a2kit's existing `LAYER_MANIFEST` +
   `A2K-LAYER` + `A2K-PKG-FRONT-DOOR` system expresses cleanly. `tach sync`
   would just snapshot today's import graph, losing the structural value.
   See proposal.md as drafted (preserved in this archive) for the longer
   reasoning.

2. **2 of 3 planned archon rules turned out redundant or out of scope
   (second scope reduction).**
   - Rule 3.1 (init purity) — genuinely new. Kept.
   - Rule 3.2 (tool returns pydantic) — **REDUNDANT** with existing
     `A2K002` (tool declares `-> str`) and `A2K011` (tool returns raw
     `dict` / `Mapping`) in `packages/lint/rules/shape.py`.
   - Rule 3.3 (no `dict[str, Any]` on internal dataclasses) — not
     covered, but deferred (BACKLOG entry filed).

3. With only one new rule to ship and the existing `packages/lint/rules/`
   harness already comprehensive, spinning up a parallel
   `tests/architecture/` harness + a `pytest-archon` dep would have been
   overengineering. The init-purity rule moved into `packages/lint/rules/
   importing.py` as `A2K-PKG-INIT-PURITY` instead, with tests in
   `tests/packages/lint/rules/test_importing.py`.

## What landed

- New lint rule `A2K-PKG-INIT-PURITY` in
  `src/a2kit/packages/lint/rules/importing.py:236` — flags `_`-prefixed
  names re-exported through `packages/<name>/__init__.py` via `__all__` or
  `from ._x import _y` patterns. Complements `A2K-PKG-FRONT-DOOR`.
- 8 new unit tests in `tests/packages/lint/rules/test_importing.py`.
- 4 grandfathered violations suppressed inline with
  `# noqa: A2K-PKG-INIT-PURITY` and documented (di, dispatch×2, ldd —
  each retired by an upcoming follow-up change).

## What was deferred

- **`dict[str, Any]` rule.** BACKLOG entry filed; pick up when a real
  case for it lands.
- **pytest-archon harness.** Not adopted. If a future import-graph rule
  surfaces that the existing `A2K-LAYER` system can't express, revisit.
- **Tach.** Not adopted. Existing system is more expressive for a2kit's
  architecture. Revisit only if Tach's interface model evolves to
  express foundational-core / facade / layer-DAG concepts.

## Where the original artifacts live

`proposal.md`, `tasks.md`, `specs/arch-fitness-functions/spec.md` in
this directory are preserved as the historical record of what was
proposed before discovery shrank the change.
