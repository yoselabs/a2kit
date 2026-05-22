## 1. README.md

- [x] 1.1 Delete the API-surface-table row for `a2kit.Cap` ("Built-in
      capability `StrEnum`. `a2kit.capabilities.register(...)`"); the
      symbol does not exist on the live surface
- [x] 1.2 Trim/refresh the "Migration from v0.x" section: drop the
      ancient v0.20-anchored rows, keep only migration notes relevant
      to a current (v0.39) consumer; point to `CHANGELOG.md` for full
      history
- [x] 1.3 Verify `tests/test_readme_symbol_drift.py` still passes
      after the row deletion

## 2. ANTIPATTERNS.md

- [x] 2.1 Rewrite antipattern #9 ("Don't ship a TOON encoder") for the
      current model: no TOON, no `formatter/toon.py`, no
      `format_hint="toon"`; the seam is `render(value, consumer)` in
      `a2kit.packages.formatter` with TSV / page-tsv wire shapes (ADR
      0014). Keep the "one seam, one upstream" lesson
- [x] 2.2 Remove the dead `a2kit.capabilities.Cap` reference from the
      retired-entry note ("old #15")
- [x] 2.3 Remove the `a2kit.capabilities.Cap` reference from
      antipattern #12's public-surface list (`App`, `Router`,
      `tool`/`read`/`write`/`list_`, ~~`Cap`~~, `ToolContext`, ...)
- [x] 2.4 Fix antipattern #14: change `report=ReportT` to the live
      `reports=` (plural) verb kwarg; change `ctx.event(...)` /
      `ctx.report(...)` method form to the `a2kit.ldd` free functions
      (`a2kit.ldd.event`, `a2kit.ldd.report`)
- [x] 2.5 Fix stale `@a2kit.tool` bare-verb mentions (removed v0.33)
      in antipattern #4 and antipattern #12 — name only the live
      `read` / `write` / `list_` verbs

## 3. OPERATIONAL_CONTRACTS.md

- [x] 3.1 Rewrite Q3 internals list: replace `app._singletons` and
      `@app.on_startup` / `@app.on_shutdown` references with the live
      DI model (app-scope `provide(T, factory)` instances; resources
      with `__aenter__`/`__aexit__`); fix the tool-author note that
      says `provide`/`singleton` to name only `provide`
- [x] 3.2 Rewrite Q7: `_meta.health` is registered via the
      `@app.health_check` decorator, not `App(name, health_tool=True)`
      (`health_tool=` was removed v0.35 and now raises `TypeError`)
- [x] 3.3 Rewrite Q8: replace `@on_startup` / `@on_shutdown` (named as
      pre-dispatch contexts) with "module-level code or a warm-up
      script"; replace the `app.singleton(Pool, make_pool)` example
      with `app.provide(Pool, make_pool)`
- [x] 3.4 Confirm Q3/Q7/Q8 are now internally consistent with the
      already-current Q-DI and Q-HealthChecks sections of the same
      file

## 4. ADR status + index

- [x] 4.1 In `docs/adr/0013-adopt-fastmcp-codemode.md`, change the
      frontmatter `status: proposed` to `status: accepted`
- [x] 4.2 In `docs/adr/0014-consumer-aware-rendering.md`, change the
      frontmatter `status: proposed` to `status: accepted`
- [x] 4.3 Confirm auth ADRs 0010-0012 stay `status: proposed` (no
      auth code in `src/`; cross-checked against `BACKLOG.md`)
- [x] 4.4 Run `make adr-index` to regenerate `docs/adr/INDEX.md`; do
      not hand-edit `INDEX.md`

## 5. Verification

- [x] 5.1 `make markdown-lint` green on `README.md`,
      `ANTIPATTERNS.md`, `OPERATIONAL_CONTRACTS.md`
- [x] 5.2 `make adr-check` green (INDEX in sync with ADR frontmatter)
- [x] 5.3 `make lint` green (includes `test_readme_symbol_drift`)
- [x] 5.4 `openspec validate refresh-stale-docs --strict`
- [x] 5.5 `openspec archive refresh-stale-docs`
