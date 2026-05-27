## 1. BDD specs (write tests first)

- [x] 1.1 Capability test `tests/capabilities/rego_policy_layer/test_extract_facts_shape.py` — running `scripts/extract_facts.py` on a fixture tree emits JSON conforming to the documented shape: `{functions: [{file, name, line, kind, is_async, is_private, ast_hash_normalized}], modules: [...], suppressions: [...]}`.
- [x] 1.2 Capability test `tests/capabilities/rego_policy_layer/test_body_dup_catches_r6.py` — running `policies/body_dup.rego` against extracted facts for the current `packages/ldd/wire.py` + `packages/context/stderr.py` returns a `deny` finding naming both locations. (RED until R6 is resolved in task 7.1; GREEN after.)
- [x] 1.3 Capability test `tests/capabilities/rego_policy_layer/test_name_collision_catches_r1.py` — running `policies/name_collision.rego` against facts for `packages/dispatch/envelope.py` + `packages/dispatch/stages.py` returns a `deny` for `_call`. (RED until R1 is resolved in task 7.2; GREEN after.)
- [x] 1.4 Capability test `tests/capabilities/rego_policy_layer/test_noqa_filters_findings.py` — a function annotated `# noqa: REGO-BODY-DUP -- intentional parallel impl, see ADR-NNNN` does NOT appear in `deny`; a `# noqa: REGO-*` without ` -- ` reason raises a structural error (REGO-* rules require reasons; matches `83819db` ` -- ` grammar).
- [x] 1.5 Capability test `tests/capabilities/rego_policy_layer/test_allowlist_drops_findings.py` — names listed in `policies/allowlist.json` with `reason` are filtered from `deny`; entries without `reason` fail allowlist load.
- [x] 1.6 Capability test `tests/capabilities/rego_policy_layer/test_a2kit_lint_rego_subcommand.py` — `a2kit lint rego src/` exits non-zero with structured findings on a tree containing a known dup; exits zero on a clean tree.

## 2. OPA bootstrap

- [x] 2.1 Add `opa` install instruction to `Makefile` `bootstrap:` target (macOS: `brew install opa`; Linux: documented `curl` line). Detect existing install, no-op if present.
- [x] 2.2 Pin OPA version (`OPA_VERSION` constant in Makefile) and verify on each `make lint` run (`opa version` parse + compare).
- [x] 2.3 Document in `docs/dev/rego-toolchain.md`: what OPA is, why Rego, how to install, how to debug a `deny` locally with `opa eval --explain notes`.

## 3. Extract-facts pipeline

- [x] 3.1 Create `scripts/extract_facts.py` — walk `src/**/*.py`, parse with `ast`, emit JSON. Keep the script <500 LOC; if it grows, split into `scripts/extract/` package.
- [x] 3.2 `ast_hash_normalized` strategy: walk function body AST, replace identifier `Name.id`, `arg.arg`, `Attribute.attr` with sentinel `_ID_`; replace literal `Constant.value` with `_LIT_`; strip type annotations; hash the resulting `ast.dump(...)` with `hashlib.sha256`. Document the strategy with examples in the script docstring.
- [x] 3.3 Suppression extraction: parse `# noqa: REGO-* -- <reason>` directives line by line during the AST walk. Re-use the existing ` -- ` grammar from `packages/lint/static.py:parse_noqa` (commit `83819db`); for REGO-* rules, a `# noqa` without ` -- ` reason is a hard error.
- [x] 3.4 Add `scripts/extract_facts.py --schema` flag that prints the JSON schema of its output. Used by tests and downstream policies.
- [x] 3.5 Caching: extract is fast (~hundreds of files, simple AST) — no cache for v1. Profile if `make lint` exceeds +2s.

## 4. Rego wrapper in `a2kit lint`

- [x] 4.1 Create `src/a2kit/packages/lint/rego.py` — `a2kit lint rego [paths...]` subcommand. Pipeline: invoke extract → write to temp file → `opa eval --bundle policies/ --input <facts.json> --format json 'data.a2kit.deny'` → parse → format as `A2K-*`-shaped findings.
- [x] 4.2 Finding format: reuse existing `A2K-*` finding dataclass; rule IDs are `REGO-BODY-DUP`, `REGO-NAME-COLLISION`, etc.
- [x] 4.3 Exit code policy: any `deny` finding → exit 1, matches `a2kit lint static` behaviour.
- [x] 4.4 Wire into `Makefile` `lint:` target after `a2kit lint static`.

## 5. Policy: `body_dup.rego`

- [x] 5.1 Author `policies/body_dup.rego` — `deny[msg]` aggregates over pairs of functions with matching `ast_hash_normalized` from different files.
- [x] 5.2 Filter: skip pairs where the hash collides on bodies <3 statements (extract.py emits `body_stmt_count` per function for this filter; tunes false-positive floor without re-tuning the hash).
- [x] 5.3 Allowlist: read `policies/allowlist.json` `body_dup` section. Each entry: `{names: [...], reason: "..."}`. Function pairs whose names both appear in any allowlist entry are dropped.
- [x] 5.4 Test fixtures: `tests/capabilities/rego_policy_layer/fixtures/body_dup_*.py` with known dup pairs and allowlist-exempted pairs.

## 6. Policy: `name_collision.rego`

- [x] 6.1 Author `policies/name_collision.rego` — `deny[msg]` aggregates over `_`-prefixed (non-dunder) function names appearing in >1 file.
- [x] 6.2 Allowlist: `policies/allowlist.json` `name_collision` section, same `{names, reason}` shape.
- [x] 6.3 Seed the allowlist with current `__init__`, `main`, and any other legitimate convergent names from a baseline run; each entry requires a one-line `reason`.

## 7. Worked-example fixes (acceptance criteria)

- [x] 7.1 **Close R6**: extract canonical `_cap_text`, `_format_kv`, `format_ldd_line` in `packages/ldd/wire.py`; replace `packages/context/stderr.py:336-348` with `from a2kit.packages.ldd.wire import ...`. Add a property-style test asserting both call paths produce identical output for the same input (defence-in-depth even with body_dup policy enforcing).
- [x] 7.2 **Close R1**: extract canonical `async def _call(fn, *args, **kwargs)` to `packages/dispatch/_invoke.py`; both `envelope.py:69` and `stages.py:33` import it.
- [x] 7.3 Re-run `make lint` — `REGO-BODY-DUP` no longer fires for R6, `REGO-NAME-COLLISION` no longer fires for R1.
- [x] 7.4 Leave other audit hits (R2, R3, R4, R5, R7, R8, R9, R13) firing for now — they'll be resolved by the `consolidate-utility-duplications` follow-up (Bundle A from `STRUCTURE_ISSUES.md`). Mark them as TODO in `STRUCTURE_ISSUES.md` status legend, NOT as `# noqa`.

## 8. jscpd removal

- [x] 8.1 Delete `.jscpd.json`, `package.json`, `pnpm-lock.yaml`, `node_modules/` (the latter via `.gitignore` already).
- [x] 8.2 Remove `pnpm install` from any docs (search: `rg -l pnpm`); none currently in `make lint` so no Makefile change.
- [x] 8.3 Document the supersession in `docs/dev/rego-toolchain.md`: "body_dup.rego covers and exceeds jscpd's catch set; calibration in 2026-05-27 STRUCTURE_ISSUES.md."

## 9. Docs + BACKLOG

- [x] 9.1 New `docs/dev/rego-toolchain.md` — when to write a Rego policy vs a native `a2kit lint` rule (the two-tier B reading: invariants in Rego, authoring guidance in native lint).
- [x] 9.2 ADR: file a new ADR documenting the Rego-as-policy-substrate decision. Cite the audit, the jscpd calibration, the OSS-reuse roadmap. Update `docs/adr/INDEX.md`.
- [x] 9.3 `BACKLOG.md` entries:
  - `policy-bundles-cross-surface` — Phase 1.5; adopt `actionlint` as native tool (correctness tier); author bespoke `policies/github_actions.rego` for SHA-pinning + permissions + vendor allowlist using `woodruffw/zizmor`'s audit catalog as the rule reference; author bespoke `policies/pyproject.rego` for dep upper-bound + license policy. Note: no plug-and-play OSS Rego bundle applies — Rego ecosystem is k8s/Terraform/Docker-centric and this repo has none of those.
  - `migrate-a2k-rules-to-rego` — Phase 2 epic; per-rule openspec changes; ordering note: simplest-to-port first (`no_dict_str_any`, `metadata_private`, `surface_registry`).
  - `consolidate-utility-duplications` — Bundle A from `STRUCTURE_ISSUES.md`; uses the now-enforced Rego policies as the regression gate.
- [x] 9.4 Update `STRUCTURE_ISSUES.md`: mark R6, R1 → `IN-FLIGHT` (this change); mark R2, R3, R4, R5, R7, R8, R9, R13 → `IN-FLIGHT` (Bundle A follow-up); add a note that body_dup + name_collision policies now enforce non-regression.

## 10. Verification

- [x] 10.1 `make bootstrap` succeeds on a clean tree (OPA install instruction works).
- [x] 10.2 `make lint` green after task 7 lands; red before.
- [x] 10.3 `make test` green — all capability tests in §1 pass.
- [x] 10.4 Manually verify: add a deliberate dup function in a fixture; confirm `REGO-BODY-DUP` fires; remove it; confirm clean.
- [x] 10.5 Manually verify: add `# noqa: REGO-NAME-COLLISION -- <reason>` on a known collision; confirm filtered. Remove the ` -- ` suffix; confirm hard error.
