## Why

An audit found the human-readable docs drifted from code reality over
~7 fast minor releases. `test_readme_symbol_drift` only checks README
*exported symbols* — it does not see prose, ADR frontmatter, or any
non-README doc. So `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`, and
the ADR statuses accumulated dead references that compile-time gates
never catch. A doc claiming a removed API teaches a consumer to write
code that crashes — the worst kind of drift. This change refreshes the
specific drifted docs the audit named.

## What Changes

- **README.md** — delete the API-surface-table row for `a2kit.Cap`
  ("Built-in capability `StrEnum`. `a2kit.capabilities.register(...)`").
  Neither `a2kit.Cap` nor `a2kit.capabilities` exists in code; the row
  escaped the symbol-drift test because `Cap` is not in `__all__` and
  the table cell wording does not match the test's symbol patterns.
  Also trim/refresh the Migration section, which still anchors at
  "v0.20" for a v0.39 project — ancient migration rows are noise now.
- **ANTIPATTERNS.md** — antipattern #9 ("Don't ship a TOON encoder")
  is entirely dead: TOON was dropped, there is no
  `formatter/toon.py`, no `format_hint="toon"`. Rewrite #9 for the
  current `render(value, consumer)` / TSV model. Remove the dead
  `a2kit.capabilities.Cap` references (retired-entry note "old #15",
  antipattern #12's public-surface list). Antipattern #14 names a
  `report=ReportT` kwarg (current kwarg is `reports=`, plural) and
  `ctx.event(...)` / `ctx.report(...)` method form (LDD is now
  `a2kit.ldd` free functions) — correct both. Fix stale `@a2kit.tool`
  bare-verb mentions (removed v0.33) in antipatterns #4 and #12.
- **OPERATIONAL_CONTRACTS.md** — Q3 and Q8 use `@app.on_startup` /
  `@app.on_shutdown` and `app.singleton(...)`; none of those exist on
  `App` (the API is `provide`, `health_check`, `add_router`). Q7 says
  `_meta.health` is registered via `App(name, health_tool=True)` —
  `health_tool=` was removed v0.35 and now raises `TypeError`; the API
  is `@app.health_check`. Rewrite Q3/Q7/Q8 examples to the current
  API, and fix the stale internals list mentioning `app._singletons`.
- **docs/adr/** — ADR 0013 (`adopt-fastmcp-codemode`) and ADR 0014
  (`consumer-aware-rendering`) carry `status: proposed` but both
  clearly SHIPPED: `packages/codemode/` exists, the `render(value,
  consumer)` seam exists, and CHANGELOG describes both as landed. Flip
  both to `status: accepted` and regenerate `docs/adr/INDEX.md` via
  `make adr-index`. ADRs 0010-0012 are auth ADRs with no auth code yet
  — they stay `proposed`.

This is a docs-only refresh. No code, no public surface, no behavior
changes. README and AGENTS.md were already refreshed for the recent
`AppBuilder`→`App` collapse — that drift is out of scope here.

## Capabilities

### New Capabilities

<!-- none — this change touches docs, not framework behavior -->

### Modified Capabilities

- `docs-code-parity`: strengthen the parity expectation so it covers
  not just README *exported symbols* but the principle that
  hand-written doc examples (in `ANTIPATTERNS.md`,
  `OPERATIONAL_CONTRACTS.md`, ADR bodies) must not show APIs that have
  been removed from the live surface. No new automated gate is added;
  the requirement records the standard the docs are now held to.

## Impact

- **Docs**: `README.md`, `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`,
  `docs/adr/0013-adopt-fastmcp-codemode.md`,
  `docs/adr/0014-consumer-aware-rendering.md`, and the auto-generated
  `docs/adr/INDEX.md` (regenerated, not hand-edited).
- **Code**: none. No `src/` change, no public surface change, no
  behavior change.
- **Decision log**: two ADR statuses move `proposed` → `accepted`,
  recording reality; no ADR content is rewritten.
- **Tooling**: `make adr-index` regenerates `INDEX.md`;
  `make markdown-lint` and `make adr-check` are the verification
  gates. `test_readme_symbol_drift` continues to pass after the
  README row deletion.
