## Why

`adopt-rego-policy-layer` (2026-05-27) landed the OPA engine with two
Python-AST policies (`body_dup`, `name_collision`). The same substrate
amortizes naturally across the non-Python surfaces a2kit ships: GitHub
Actions workflows (supply-chain risk: unpinned SHAs, over-broad
`permissions:`, vendor sprawl), and `pyproject.toml` (dep upper-bound
discipline, license allowlist). Adding these now — while the Rego
pipeline is hot in head and the audit ledger is fresh — costs ~150 LOC
of policy + a small extract extension; deferring means re-learning the
extract/policy/wire seam later.

Separately, GitHub Actions has a community standard for syntax /
correctness checking (`actionlint`) that the project should adopt as
a native Go binary alongside `opa`. The Rego layer sits on top for
project-specific policy that `actionlint` does not encode.

## What Changes

- Add `actionlint` (single Go binary, pinned in Makefile, validated by
  `make actionlint-check` matching the existing `make opa-check`
  pattern). Wire it into `make lint` as a gate for
  `.github/workflows/*.yml`.
- Extend `scripts/extract_facts.py` with a new top-level `workflows:`
  collection — one entry per `.github/workflows/*.yml`, with
  `{file, name, jobs: [{name, steps: [{uses, with_keys, has_pinned_sha,
  permissions}]}], permissions, on}`.
- Extend `scripts/extract_facts.py` with a new top-level `pyproject:`
  collection: `{dependencies: [{name, spec, has_upper_bound}],
  optional_dependencies: {...}, dev_dependencies: [...]}`.
- Add `policies/github_actions.rego` with three starter requirements:
  - REGO-GHA-PIN-SHA: every `uses:` step on a third-party action SHALL
    be pinned to a 40-char SHA (not a tag/branch). Vendor allowlist
    (`actions/*`, `astral-sh/*`) loaded from `policies/data.json`.
  - REGO-GHA-PERMISSIONS: every workflow SHALL declare a top-level
    `permissions:` block. No implicit `write-all`.
  - REGO-GHA-VENDOR-ALLOW: third-party `uses:` vendors not on the
    allowlist SHALL be denied.
- Add `policies/pyproject.rego` with one starter requirement:
  - REGO-PYPROJECT-UPPER-BOUND: every runtime dep in
    `[project.dependencies]` SHALL declare an upper bound (`<X.Y` or
    `~=X.Y`). Optional + dev deps exempt.
- License-allowlist policy is **deferred** until `uv` exposes resolved
  licenses as a fact source; tracked in BACKLOG.
- Allowlist entries (if any during pilot) land in `policies/data.json`
  under `a2kit.allowlist.<policy_name>` with required `reason`.
- ADR 0026 records the cross-surface extension: the engine is the same,
  the fact-extractor grows new top-level collections, the wire
  (`a2kit lint rego`) is unchanged.

## Capabilities

### New Capabilities

- `actionlint-toolchain`: native `actionlint` adoption as a `make
  lint` gate for `.github/workflows/*.yml`, version-pinned in
  Makefile, with the same shape as the OPA install/verify pattern.

### Modified Capabilities

- `rego-policy-layer`: `extract_facts.py` schema gains two new
  top-level collections (`workflows`, `pyproject`); two new policies
  (`github_actions.rego`, `pyproject.rego`) become part of the policy
  bundle and execute under the same `a2kit lint rego` wrapper.

## Impact

- New Makefile targets: `actionlint-check`, `actionlint-install-hint`,
  `make lint` chains `actionlint` before the rego invocation.
- `scripts/extract_facts.py` grows two readers (YAML for workflows,
  TOML for pyproject). Adds `pyyaml` if not already present (stdlib
  `tomllib` covers pyproject). Pure-function invariant preserved.
- `policies/` gains two `.rego` files + helpers + tests.
- `tests/capabilities/rego_policy_layer/` gains 4 scenario files
  covering the new policies.
- `policies/data.json` gains `github_actions.vendor_allowlist` array
  (`actions`, `astral-sh`, `denoland`, `pnpm`, others as discovered)
  and `policies/data.json` `a2kit.allowlist.{github_actions_pin,
  github_actions_vendor, pyproject_upper_bound}` arrays.
- `docs/dev/rego-toolchain.md` documents the two new policies and the
  vendor-allowlist mechanism.
- `docs/adr/0026-cross-surface-policy-bundles.md` records the
  Y-statement.
- `STRUCTURE_ISSUES.md` reference: no audit entry directly drove
  this; it's Phase 1.5 from ADR 0024's follow-up plan.
- Cross-ref: `woodruffw/zizmor` audit catalog is the rule reference for
  REGO-GHA-* policies; we author bespoke Rego rather than wrap zizmor
  to keep the substrate (OPA) singular.
