## 1. actionlint adoption

- [x] 1.1 Add `ACTIONLINT_VERSION` (pin to current stable, e.g. 1.7.4) to `Makefile`
- [x] 1.2 Add `make actionlint-check` target with install-hint output (mirror `opa-check`)
- [x] 1.3 Extend `make bootstrap` to include actionlint in the pre-flight report
- [x] 1.4 Add `actionlint` invocation to `make lint`, ordered before the rego layer
- [x] 1.5 Install actionlint locally and verify `make actionlint-check` exits 0
- [x] 1.6 Run `actionlint` against existing `.github/workflows/*.yml` and fix or allowlist findings

## 2. Extract facts extension — workflows

- [x] 2.1 BDD: write failing scenario test for `workflows` collection (see rego-policy-layer spec scenarios)
- [x] 2.2 Add `pyyaml` to project lint-deps if not already present (verify via `uv pip list`)
- [x] 2.3 In `scripts/extract_facts.py` add `_collect_workflows()`: glob `.github/workflows/*.yml`, parse with `yaml.safe_load`, walk jobs/steps, compute `has_pinned_sha` (40-char hex) + `vendor` (first `/`-component of `uses`)
- [x] 2.4 Add `workflows` to the JSON output and to `--schema`
- [x] 2.5 Verify byte-reproducibility scenario still holds (rerun twice, diff)
- [x] 2.6 Make scenarios in 2.1 pass

## 3. Extract facts extension — pyproject

- [x] 3.1 BDD: write failing scenario test for `pyproject` collection (upper-bound detection)
- [x] 3.2 In `scripts/extract_facts.py` add `_collect_pyproject()`: read `pyproject.toml` via `tomllib`, walk `[project.dependencies]` + `[project.optional-dependencies]` + `[build-system].requires`, parse each spec, set `has_upper_bound` per the rule (`<`, `<=`, `~=` present)
- [x] 3.3 Add `pyproject` to JSON output and `--schema`
- [x] 3.4 Make scenarios in 3.1 pass

## 4. Policy authoring — github_actions.rego

- [x] 4.1 BDD: write failing capability tests for REGO-GHA-PIN-SHA, REGO-GHA-PERMISSIONS, REGO-GHA-VENDOR-ALLOW under `tests/capabilities/rego_policy_layer/`
- [x] 4.2 Author `policies/github_actions.rego` with `package a2kit`, importing future keywords
- [x] 4.3 Implement REGO-GHA-PIN-SHA rule using `workflows[_].jobs[_].steps[_]` walk + allowlist filter
- [x] 4.4 Implement REGO-GHA-PERMISSIONS rule
- [x] 4.5 Implement REGO-GHA-VENDOR-ALLOW rule
- [x] 4.6 Seed `policies/data.json` `a2kit.allowlist.github_actions_vendor` with `actions` + `astral-sh` (+ any other vendors actually used in repo) each with `reason`
- [x] 4.7 Make scenarios in 4.1 pass

## 5. Policy authoring — pyproject.rego

- [x] 5.1 BDD: write failing capability test for REGO-PYPROJECT-UPPER-BOUND
- [x] 5.2 Author `policies/pyproject.rego` with single rule walking `pyproject.dependencies`, filtering on `has_upper_bound == false`, intersecting with allowlist
- [x] 5.3 Make scenarios in 5.1 pass

## 6. Repo cleanup (if any policies fire on current state)

- [x] 6.1 Run `a2kit lint rego` against current tree
- [x] 6.2 For each finding: either fix (preferred) or add `policies/data.json` allowlist entry with non-empty `reason`
- [x] 6.3 Re-run; expect green

## 7. Docs + ADR

- [x] 7.1 Author `docs/adr/0026-cross-surface-policy-bundles.md` (Y-statement format)
- [x] 7.2 Update `docs/dev/rego-toolchain.md`: add §"Cross-surface policies" describing workflows + pyproject domains
- [x] 7.3 Regenerate `docs/adr/INDEX.md`
- [x] 7.4 Regenerate `docs/COMPONENT_MAP.md` if extract structure changed enough to matter
- [x] 7.5 Add `Unreleased` entry to `CHANGELOG.md` summarizing actionlint + 2 new policies
- [x] 7.6 Mark BACKLOG `policy-bundles-cross-surface` entry as drained (replace with brief HTML comment pointing to archive)

## 8. CI integration

- [x] 8.1 If GitHub Actions CI workflow exists for this repo: add actionlint install step
- [x] 8.2 Verify `make lint` is the gate (no separate jobs for actionlint/rego — single chain)

## 9. Final validation

- [x] 9.1 `make lint` exits 0
- [x] 9.2 `make test` exits 0, no regressions
- [x] 9.3 `make typecheck` clean
- [x] 9.4 `openspec validate policy-bundles-cross-surface --strict` passes
