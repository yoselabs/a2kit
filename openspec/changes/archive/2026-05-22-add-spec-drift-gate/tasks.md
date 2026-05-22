## 1. Audit the spec tree (worklist seed)

- [x] 1.1 Enumerate `openspec/specs/*/spec.md` and grep each for
      backtick-quoted symbols matching the checkable shapes (dotted
      a2kit paths, `App.`/`app.`/`Router.`/`Container.` accesses,
      `A2K-` lint-rule codes)
- [x] 1.2 For each extracted symbol, check resolution against the live
      `a2kit` surface; record the unresolved set — this becomes the
      grandfathered-drift allowlist and the `reconcile-stale-specs`
      worklist seed
- [x] 1.3 Confirm the audit reproduces the known ~18 drifted specs
      (`a2kit.Param`, `Container._snapshot` / `_restore` / `_override`,
      `App.singleton`, `@app.on_startup`, `A2K-DI-CHAIN` /
      `A2K-DI-PROVIDER`); reconcile any audit gaps

## 2. Build the spec-drift gate (BDD-first)

- [x] 2.1 Write `tests/test_spec_symbol_drift.py` failing-first tests:
      a fixture spec citing a dead dotted symbol fails the gate; a dead
      `Container.x` access fails; a dead `A2K-` rule code fails; an
      allowlisted name passes; an illustrative `Lazy[T]` / `pydantic.X`
      token is not checked
- [x] 2.2 Implement the spec-file scanner: glob `openspec/specs/*/spec.md`,
      extract backtick-quoted (code-font) spans with their line numbers
- [x] 2.3 Implement the checkable-symbol extractor and skip rules per
      design D3 — dotted a2kit paths, canonical-type accesses, `A2K-`
      lint codes are checkable; bare words, string literals, paths,
      shell, type-annotation fragments, non-a2kit-prefixed tokens are
      skipped
- [x] 2.4 Implement resolution: `hasattr` / `importlib` for dotted
      paths and canonical-type accesses (bind against live `a2kit.App`,
      `Router`, `Container`); resolve `A2K-` codes against the live
      a2kit lint-rule registry
- [x] 2.5 Implement the allowlist as a single co-located constant
      (example-only names, tombstone migration targets, grandfathered
      drift); every entry carries a why-comment, grandfathered entries
      carry a `# reconcile:` tag
- [x] 2.6 Implement the failure message: one line per unresolved symbol
      as `openspec/specs/<cap>/spec.md:<line> — <symbol>: <reason>`
- [x] 2.7 Seed the allowlist with the audit's grandfathered-drift set
      (task 1.2) so the gate lands green against today's specs

## 3. Wire the gate into the pipeline

- [x] 3.1 Add `uv run pytest tests/test_spec_symbol_drift.py --no-cov -q`
      to the `lint` target in `Makefile`, immediately after the
      existing README symbol-drift gate line
- [x] 3.2 Confirm `make lint`, `make check`, CI, and the pre-commit
      hook all execute the gate with no further wiring

## 4. Tombstone-lifecycle ADR

- [x] 4.1 Write `docs/adr/0018-tombstone-lifecycle.md` (next free
      number; 0001–0017 exist) with valid YAML frontmatter per
      `docs/adr/schema.json` (`id: "0018"`, `status: accepted`, `date`,
      `last_reviewed`, `supersedes: []`, `superseded_by: null`, `tags`,
      `deciders`) and a Nygard-style body
- [x] 4.2 Record decision 1 — tombstones are permanent but cheap:
      data-driven (one removed-name registry dict per module + one
      module-level `__getattr__`), NOT hand-written per-method
      raise-stubs
- [x] 4.3 Record decision 2 — removed-surface behavior is NOT a
      living-spec Requirement; if specced at all it is a short-lived
      `ADDED` requirement in the removing change, `REMOVED` a couple of
      minors later; name the current `test-container-peek` /
      `app-builder-runtime` tombstone-as-requirement specs as the
      anti-pattern
- [x] 4.4 Record decision 3 — a superseded capability spec is DELETED
      from `openspec/specs/`, not left as an emptied husk of `REMOVED`
      requirements; the OpenSpec archive preserves history
- [x] 4.5 Run `make adr-index` to regenerate `docs/adr/INDEX.md`;
      `make adr-check` green

## 5. Validate and wrap up

- [x] 5.1 `make lint` green (includes the new gate against the
      grandfathered allowlist)
- [x] 5.2 `make check` and `make markdown-lint` green
- [x] 5.3 `openspec validate add-spec-drift-gate --strict`
- [x] 5.4 Note in `BACKLOG.md` (or the change record) that
      `reconcile-stale-specs` is the required follow-up — it consumes
      this gate's failure list and shrinks the grandfathered allowlist
- [x] 5.5 `openspec archive add-spec-drift-gate` (after
      `reconcile-stale-specs` is queued)
