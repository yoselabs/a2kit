---
id: "0026"
status: accepted
date: 2026-05-28
last_reviewed: 2026-05-28
supersedes: []
superseded_by: null
tags: [lint, policy, tooling, supply-chain]
deciders: [Denis Tomilin]
---

# ADR 0026: Cross-surface policy bundles (workflows + pyproject)

## Status

Accepted, 2026-05-28. Implemented in change
`policy-bundles-cross-surface`.

## Summary

In the context of `adopt-rego-policy-layer` (ADR 0024) having shipped the
OPA engine with Python-AST facts only, facing the fact that the
project's highest-leverage non-Python surfaces (GitHub Actions
workflows, `pyproject.toml`) currently have zero policy coverage and
that re-learning the extract/policy seam later is more expensive than
extending now, we decided for **growing `scripts/extract_facts.py` with
two new top-level collections (`workflows`, `pyproject`) and adding two
new policy files (`github_actions.rego`, `pyproject.rego`) under the
existing OPA engine, alongside adopting `actionlint` as a native
syntax/correctness gate, and against wrapping `actionlint` or `zizmor`
as Rego inputs, to achieve a single substrate (OPA) covering both
code and configuration surfaces with reproducible enforcement.

## The problem

The 2026-05-27 audit gave us a Rego pipeline that polices Python
codebase invariants (body-dup, name-collision). Two adjacent surfaces
are unguarded:

- **`.github/workflows/*.yml`** — supply-chain risk surface. Unpinned
  third-party actions (`@v1`, `@main`) execute mutable code in CI. No
  top-level `permissions:` block silently grants implicit
  `contents: write`. Vendor sprawl (any GitHub user can ship an
  action) compounds blast radius.
- **`pyproject.toml`** — runtime dependency hygiene. Bare specifiers
  (`httpx`, `pydantic>=2`) absorb breaking changes silently on the
  next `uv sync` or downstream install.

Both surfaces are *configuration*, not code. Both have the same
property as the Python audit: **invariants over a parseable shape**,
not authoring guidance. The Rego substrate is the right fit; growing
it costs one extractor extension + one policy file per surface.

## Decision

### actionlint stays a native binary

`actionlint` is a parser + correctness checker (~3000 lines of Go,
including shellcheck integration). Re-implementing in Rego would
duplicate engineering for zero gain. It runs as a `make lint` gate
ahead of the Rego layer (fail-fast on syntax errors before semantic
policies execute).

Pinned in `Makefile` (`ACTIONLINT_VERSION`), validated via
`make actionlint-check` mirroring the existing `make opa-check`
pattern.

### Two policy files, not one

`policies/github_actions.rego` carries three rules
(REGO-GHA-PIN-SHA, REGO-GHA-PERMISSIONS, REGO-GHA-VENDOR-ALLOW).
`policies/pyproject.rego` carries one (REGO-PYPROJECT-UPPER-BOUND).
Splitting per-surface (not per-rule) keeps shared helpers (e.g.
vendor allowlist filter) inside one file while keeping the blast
radius of "temporarily disable workflow policies" tight.

### Extract pre-computes derived fields

The extractor computes `has_pinned_sha` (40-char hex check) and
`vendor` (first `/`-component of `uses:`) at extract time, not in
Rego. Rego stays declarative; string manipulation lives in Python
where it's cheap to test. Same pattern for pyproject's
`has_upper_bound` (regex match for `<`, `<=`, `~=`).

### Allowlists in policies/data.json

Three new allowlist sections, all with the existing required
`reason` field:

- `github_actions_vendor` — vendors permitted to appear in `uses:`
  at all (seeded with `actions` + `astral-sh`).
- `github_actions_vendor_unpinned` — vendors permitted to skip the
  SHA pin (seeded with `actions` + `astral-sh` — solo repo, CI-only
  trust boundary; revisit if release artifacts ship).
- `pyproject_upper_bound` — runtime deps exempt from upper-bound
  rule (seeded with `a2effect` — workspace member, resolved from
  local checkout not PyPI).

### Runtime-deps-only for pyproject

`[project.dependencies]` is gated. `[project.optional-dependencies]`
and `[build-system].requires` are exempt. Optional groups are opt-in
per-consumer; build deps don't ship to runtime.

### Pipeline order

`make lint` chain: `a2kit lint static` → `actionlint` →
`a2kit lint rego`. Fast-fail at each stage.

## What this is not

- Not a zizmor wrapper. We borrow zizmor's audit catalog as rule
  reference but author bespoke Rego to keep one substrate.
- Not a license-allowlist gate. Blocked on `uv` exposing resolved
  licenses cleanly; tracked in BACKLOG.
- Not composite-action or reusable-workflow auditing. Scope creep
  for v1.
- Not lockfile auditing. Different fact source (`uv.lock`); separate
  proposal when needed.

## Forces

| Force | Pull |
|---|---|
| Supply-chain risk on `.github/workflows/*.yml` is uncovered | toward growing the Rego layer |
| `actionlint` exists, is community-standard, native Go | toward adopting it as a separate gate |
| One substrate (OPA) lowers operational cost | against fragmenting per-surface engines |
| Solo project, minimize toolchain weight | against any new binary — mitigated by single-binary install |
| zizmor exists as a hand-rolled GHA auditor | against re-implementing — answered by "we use its catalog, not its engine" |
| `pyproject` upper-bound rule is small | toward including it (same change, low extra cost) |
| Extract growing non-Python surfaces inflates schema | accepted — schema growth IS how the substrate generalizes |

## Costs accepted

- **New binary in bootstrap:** `actionlint` joins `opa`. Single Go
  binary; pinned in Makefile; install hints for macOS/Linux.
- **Two new extract dependencies:** `pyyaml` (transitive via fastmcp,
  no new declared dep needed) and `tomllib` (stdlib).
- **Two new policy files + helpers.** ~150 LOC of `.rego` total.
- **One workflow + 5 pyproject deps updated** to satisfy new
  policies on first run.

## Consequences

- `make lint` exit code now reflects workflow + pyproject hygiene in
  addition to Python invariants.
- `a2kit lint rego` schema gains `workflows` + `pyproject`
  collections; published via `--schema` for tooling that wants to
  introspect.
- Adding the next domain (e.g. Dockerfile, `mise.toml`,
  `.pre-commit-config.yaml`) is mechanical: extend extract, author
  policy file, write capability tests.

## Related decisions

- ADR 0024 (Rego as architectural-policy substrate) — this ADR is
  Phase 1.5 from its follow-up plan.
- BACKLOG `migrate-a2k-rules-to-rego` — Phase 2; orthogonal to this
  change.
- BACKLOG `policy-bundles-cross-surface` — drained by this change.

## References

- `openspec/changes/policy-bundles-cross-surface/` — this change's
  spec + design.
- `docs/dev/rego-toolchain.md` — toolchain how-to (updated for the
  new policies).
- `STRUCTURE_ISSUES.md` — the 2026-05-27 audit + jscpd calibration.
- `actionlint`: <https://github.com/rhysd/actionlint>
- zizmor (GHA audit catalog reference):
  <https://woodruffw.github.io/zizmor/audits/>
