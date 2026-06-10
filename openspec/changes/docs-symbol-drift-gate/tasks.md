# Tasks — docs-symbol-drift-gate

## 1. Shared engine (no redundancy)

- [x] 1.1 Extract the spec gate's extraction/resolution into
      `tests/support/symbol_drift.py` with a
      `collect_drift(text, *, label, allowlist)` entrypoint.
- [x] 1.2 Refactor `tests/test_spec_symbol_drift.py` to bind the shared
      engine with its allowlist; keep its BDD unit tests + main test green.

## 2. Docs gate (RED → GREEN)

- [x] 2.1 Add `tests/test_docs_symbol_drift.py` scanning `ANTIPATTERNS.md`,
      `OPERATIONAL_CONTRACTS.md`, `docs/patterns/*.md`; exclude
      `docs/adr/*.md`. Allowlist genuine non-symbols only (logger names,
      AK013 sentinel marker strings). Watch it fail on the live drift.
- [x] 2.2 Reconcile the drift to the current surface: `a2kit.ldd.*` →
      `a2kit.log.*`; drop the deleted `event`/`report`/`set_ldd`/`add_sink`/
      `EventRegistry`/`on_shutdown`; `Container.dispatch` → `call_scope`;
      `ldd_state_for_call` → `bind_call_scope`; retired `A2K-CORE-CLEAN` /
      `A2K013` → `AK###`. Delete obsolete sections; drop the resolving
      prefix on deliberately-non-existent "X does not exist" examples.
- [x] 2.3 Gate green: zero drift across all scanned docs.

## 3. Wiring

- [x] 3.1 Add the docs gate to the `make lint` target.

## 4. Spec

- [x] 4.1 ADD requirement: living narrative docs have an automated
      symbol-drift gate (ANTIPATTERNS / OPERATIONAL_CONTRACTS /
      docs-patterns; ADRs excluded; shared engine; runs under make lint).
- [x] 4.2 MODIFY "README accurately reflects the v0.33 public surface":
      scope the removed-API standard to the living-narrative docs and
      EXEMPT ADR bodies (historical records); keep the ADR-frontmatter-
      status requirement.
- [x] 4.3 `openspec validate docs-symbol-drift-gate --strict` passes.

## 5. Verify

- [x] 5.1 Full suite + spec-drift + docs-drift + ruff + ty + a2kit-lint
      green; `make lint` green.
