# Tasks — trim top-level namespace

## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint` + `make test`.
- [ ] 0.2 `prune-dead-decorator-surface` has landed (removed
      `Cap`/`capabilities` — those are NOT demoted; they're deleted).
- [ ] 0.3 Inventory downstream import sites: grep a2web, a2db,
      a2atlassian, fox for each demotion target.

## 1. Demote introspection symbols

- [ ] 1.1 Remove from `src/a2kit/__init__.py` `_LAZY_ATTRS`:
      `A2KitMeta`, `RouterRegistry`, `UNRESOLVED`.
- [ ] 1.2 Remove same from `__all__`.
- [ ] 1.3 Update `TYPE_CHECKING` imports in `__init__.py` to drop
      those three.
- [ ] 1.4 Verify they remain importable from owning modules:
      `from a2kit.metadata import A2KitMeta` etc.

## 2. Demote exception subclasses

- [ ] 2.1 Remove from `src/a2kit/__init__.py` `_LAZY_ATTRS` and
      `__all__`: `ToolCallContamination`,
      `InvalidToolReturnTypeError`, `InvalidFilterExpression`,
      `ReportTypeNotDeclared`, `ReportTypeMismatch`.
- [ ] 2.2 **KEEP** `A2KitError` at top-level.
- [ ] 2.3 Update `TYPE_CHECKING` imports in `__init__.py`.
- [ ] 2.4 Verify importable from `a2kit.exceptions`.

## 3. Demote LDD sink-author names

- [ ] 3.1 Decide between two shapes (pick one in design review):
      - **3.1.a** Drop the four names from `src/a2kit/ldd.py`
        re-exports entirely. Authors import from
        `a2kit.packages.ldd`.
      - **3.1.b** Create `src/a2kit/ldd/sinks.py` that re-exports
        `LddEmission`, `LddSink`, `format_ldd_line`,
        `ldd_state_for_call` from `a2kit.packages.ldd`. Convert
        `a2kit.ldd` from a module to a package.
- [ ] 3.2 Update `src/a2kit/ldd.py` `__all__` to drop the four names.
- [ ] 3.3 Verify the live author surface (`event`, `report`, `log`,
      `info`/`warning`/`error`/`debug`, `EventRegistry`) remains at
      `a2kit.ldd.*`.

## 4. Update in-repo callers

- [ ] 4.1 In `tests/test_app_lifecycle_and_di.py`, swap
      `from a2kit.app import App, UNRESOLVED` → already correct.
      Audit for `from a2kit import UNRESOLVED` and fix.
- [ ] 4.2 Same audit for `A2KitMeta`, `RouterRegistry`, and the
      five demoted exceptions across `tests/`.
- [ ] 4.3 Audit `examples/` for any demoted-symbol imports.

## 5. Lint rule

- [ ] 5.1 Add a lint rule that flags `from a2kit import <demoted>`
      pointing at the owning-module form. Catches downstream
      stragglers at lint time.
- [ ] 5.2 Test the rule fires on a fixture.

## 6. Documentation

- [ ] 6.1 Update README (if it lists top-level exports) to reflect
      the trimmed surface.
- [ ] 6.2 Add a "Top-level surface" section to `docs/` documenting
      the kept-vs-demoted split.

## 7. Verify

- [ ] 7.1 `make lint` clean.
- [ ] 7.2 `make test` — all green.
- [ ] 7.3 `python -c "import a2kit; a2kit.A2KitMeta"` raises
      `AttributeError` (demoted).
- [ ] 7.4 `python -c "from a2kit.metadata import A2KitMeta; print(A2KitMeta)"`
      works (still importable).
- [ ] 7.5 Cold-start: `python -c "import a2kit; print('ok')"`
      timing unchanged or better.

## 8. Release notes + downstream

- [ ] 8.1 CHANGELOG entry under "Breaking" with full demotion
      table and migration imports.
- [ ] 8.2 Notify downstream maintainers with the table.
