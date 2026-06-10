# docs-symbol-drift-gate

## Why

The `docs-code-parity` capability already declares that the non-README
living docs (`ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`) must name only
live APIs — but that standard was **reader-enforced**, with an automated
gate only for `README.md`. So the docs silently rotted: the 2026-06-03
stdlib-logging refounding renamed `a2kit.ldd.*` → `a2kit.log.*` and deleted
`event`/`report`/`set_ldd`/`add_sink`, and 34 references to the removed
surface accumulated across the living docs (plus a stale
`docs/patterns/operator-and-wire-sinks.md`, deleted last session). No gate
caught any of it.

This change automates the existing standard: a `docs/`-scanning sibling of
the README and spec drift gates, sharing one extraction/resolution engine.

It also fixes a wrong claim in the current spec: that doc-parity applies to
"ADR bodies under `docs/adr/`". An ADR is a historical record and rightly
cites the names it removed (ADR 0017 cites `a2kit.AppBuilder`). ADR bodies
are EXEMPT from the gate and the standard; only ADR frontmatter `status`
must track reality.

## What changes

- Extract the spec gate's extraction/resolution engine into
  `tests/support/symbol_drift.py` (one engine, no second copy); the spec
  gate now binds it with its allowlist.
- Add `tests/test_docs_symbol_drift.py` scanning `ANTIPATTERNS.md`,
  `OPERATIONAL_CONTRACTS.md`, and `docs/patterns/*.md`. `docs/adr/*.md` is
  excluded by design.
- Reconcile the 34 stale references in the living docs to the current
  surface (NO backward-compat shims).
- Wire the new gate into `make lint`.
- **Spec:** add the automated-gate requirement; modify the existing
  "README accurately reflects…" requirement to exempt ADR bodies.

## Impact

- Affected capability: `docs-code-parity`.
- New: `tests/support/symbol_drift.py`, `tests/test_docs_symbol_drift.py`.
- Docs reconciled: `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`.
- No `src/` behavior change; tooling + docs only.
