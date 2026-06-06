# Tasks — ruff-compatible-lint-codes

BDD-first / TDD red→green. The code-shape and co-suppression invariants
get failing tests *before* the rename; the bulk-migration and snapshot
regeneration carry an explicit **no-silent-truncation** guard.

## 1. Code-shape contract (RED → GREEN)

- [ ] 1.1 Write a failing test that asserts **every** a2kit lint code
      (static `AK*`, runtime `AKR*`, rego `RG*`) matches the ruff noqa
      grammar `^[A-Z]+[0-9]+$`. Run it against today's codes → RED
      (`A2K-LAYER`, `REGO-NAME-COLLISION`, etc. fail the regex).
- [ ] 1.2 Write a failing test that the three reserved prefixes
      (`AK`, `AKR`, `RG`) are pairwise non-overlapping and that no code
      collides across families (e.g. no `AK014` defined twice).
- [ ] 1.3 GREEN: rename the code constants — `static.py`
      (`A2K014`→`AK014`, dashed `A2K-*`→`AK2xx`), `runtime.py`
      (`A2KR001`→`AKR001`), `_bundle/extract_facts.py`
      (`REGO_RULE_PREFIX`/`RG` band), `_bundle/policies/*.rego`
      (`REGO-*`→`RG*` rule-ID literals). Tests 1.1–1.2 pass.

## 2. Inline-suppression grammar (RED → GREEN)

- [ ] 2.1 Write a failing test: a line `# noqa: AK200, S603` is parsed by
      a2kit's `parse_noqa` into `{AK200, S603}`, `suppressed("AK200",
      line)` is True, and the foreign `S603` is inert for a2kit (does not
      match any a2kit rule, does not raise). RED until the parser accepts
      the new prefixes.
- [ ] 2.2 Write a failing test that ruff and a2kit **agree on the same
      mixed line** — i.e. the co-suppression line round-trips through
      ruff's noqa parser without ruff treating the a2kit code as a parse
      error (assert via a small ruff invocation / golden, or assert the
      a2kit code matches `[A-Z]+[0-9]+` so ruff's grammar accepts it as an
      unknown-but-well-formed code). RED against a dashed code.
- [ ] 2.3 Write a failing test for the `RG*` mandatory-` -- reason` rule:
      `# noqa: RG001` (no reason) is a hard structural error;
      `# noqa: RG001 -- why` is accepted. RED until the rego extractor
      keys on `RG` instead of `REGO-`.
- [ ] 2.4 GREEN: extend `parse_noqa` / the rego extractor to the new
      prefixes; the existing comma + ` -- ` parser is grammar-agnostic, so
      this is wiring the new prefixes through, not rewriting the parser.

## 3. Legacy alias table (RED → GREEN)

- [ ] 3.1 Write a failing test that `LEGACY_CODE_ALIASES` is **complete
      and lossless**: every legacy code (`A2K*`, `A2KR*`, `REGO-*`) has
      exactly one entry, every value matches `^[A-Z]+[0-9]+$`, and the
      map is injective (no two legacy codes share a new code). RED until
      the table exists.
- [ ] 3.2 Write a failing test that a legacy suppression still resolves:
      `# noqa: A2K-LAYER` suppresses the renamed `AK200` rule, and a
      legacy `disabled = ["A2K014"]` config entry disables `AK014`,
      during the deprecation window. RED.
- [ ] 3.3 GREEN: add `LEGACY_CODE_ALIASES` and normalize recognized
      legacy codes to their new code in `parse_noqa` + the disable-list
      reader. Tests 3.1–3.2 pass. Emitted findings always use the **new**
      code (assert a finding's `.rule` is never a legacy spelling).

## 4. Bulk-suppression migration (no silent truncation)

- [ ] 4.1 Write a guard test that runs BEFORE/AFTER the sweep: the count
      of `# noqa:` lines across `src/` + `tests/` is **identical**, and
      every code present after the sweep is a value (new code) in the
      alias table — never a legacy spelling and never empty. A dropped or
      unrecognized suppression FAILS the test (no silent truncation).
- [ ] 4.2 Run the scripted 1:1 rename over every `# noqa:` site in
      `src/` and `tests/`, driven by the alias table. The script aborts
      on any code not in the table rather than skipping it.
- [ ] 4.3 Assert the ` -- <reason>` suffix on each rewritten line is
      preserved byte-for-byte (reason text unchanged; only the code token
      before it changes).
- [ ] 4.4 Diff-review the sweep: confirm no `# noqa:` line lost a code or
      a reason.

## 5. Snapshot / fixture regeneration (no silent truncation)

- [ ] 5.1 Write a guard test: the **set of rules represented** in the
      lint snapshot fixtures is identical before/after regeneration (only
      the code spelling changes). A rule disappearing from the snapshots
      FAILS the test.
- [ ] 5.2 Regenerate the lint snapshot fixtures against the new codes.
- [ ] 5.3 Confirm the regenerated snapshots contain only new-shape codes
      (`^[A-Z]+[0-9]+$`), no legacy spelling leaks into a fixture.

## 6. Config + entry-points

- [ ] 6.1 Update `pyproject.toml [tool.a2kit.lint]` disable lists to new
      codes (legacy entries still resolve via the alias table, but the
      canonical config uses new codes).
- [ ] 6.2 Update the `[project.entry-points."a2lint.rules"]` keys for the
      `raises-closure-lint` rules (`A2K-RAISES-*` → `AK*`) so entry-point
      discovery returns the new codes.

## 7. Docs + spec parity

- [ ] 7.1 Document the reserved prefixes (`AK`/`AKR`/`RG`) and the
      ruff-superset noqa grammar where the lint codes are documented
      (README / lint package docstring).
- [ ] 7.2 Confirm the three MODIFIED specs (`rego-policy-layer`,
      `module-layout-discipline`, `raises-closure-lint`) match the
      shipped code strings; `openspec validate ruff-compatible-lint-codes
      --strict` is green.

## 8. Verify (GREEN)

- [ ] 8.1 All new tests from §1–§5 pass.
- [ ] 8.2 Full suite green, output pristine; `a2kit lint static` /
      `ty check src/` / ruff gates green on all touched files.
- [ ] 8.3 Forward-compat seam: the dup-name lint rule (ADR 0028 decision
      6 / `validate-composition`) can now adopt a ruff-safe `AK*` code
      with no further grammar work.
