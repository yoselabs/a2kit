## Context

`adopt-rego-policy-layer` shipped a generic OPA-eval pipeline:
`scripts/extract_facts.py → opa eval --bundle policies/ → LintMessage`.
The fact-extractor today emits Python-AST facts only
(`functions`, `modules`, `suppressions`). The substrate is
fact-source-agnostic by construction — adding new policy domains is
mechanical: (a) teach the extractor to read the new source, (b) author
a `.rego` file, (c) write capability tests.

GitHub Actions is the highest-leverage second surface: the project's
attack surface for supply-chain compromise is workflow YAML, and the
industry has converged on `actionlint` for syntax/correctness and
on the zizmor catalog for project-policy patterns (SHA-pinning,
permissions, vendor allowlist). `pyproject.toml` is a smaller but
real lever: dep upper-bound discipline catches sloppy
specifiers before they break a deploy.

This change is **not** the migration of A2K-* rules to Rego (that's
`migrate-a2k-rules-to-rego`, opportunistic). It's the breadth move:
prove the substrate generalizes across surfaces.

## Goals / Non-Goals

**Goals:**

- Demonstrate the Rego substrate generalizes from Python-AST facts to
  YAML (workflows) and TOML (pyproject) without changes to the wire
  (`a2kit lint rego` invocation) or the suppression mechanism (`# noqa
  -- reason`).
- Catch supply-chain risks on `.github/workflows/*.yml` (unpinned SHAs,
  permissive `permissions:`, vendor sprawl) as `make lint` failures.
- Adopt `actionlint` as the syntax/correctness gate, separately from
  Rego project policy. Two-tier on the workflow surface mirrors the
  existing Python two-tier (`a2kit lint static` + `a2kit lint rego`).
- Catch dep upper-bound omissions on `[project.dependencies]` before
  they bite.

**Non-Goals:**

- Wrapping `zizmor` itself. We author bespoke Rego using its catalog as
  rule reference. Rationale: one substrate (OPA), one wire.
- License-allowlist enforcement. Blocked on `uv` exposing resolved
  licenses cleanly; tracked in BACKLOG.
- Composite-action / reusable-workflow auditing. Scope creep for v1.
- Lockfile (`uv.lock`) auditing. Out of scope — different fact source.

## Decisions

### Decision 1: actionlint is a native binary, NOT a Rego policy

`actionlint` is a parser + correctness checker (typo detection, shell
script integration via `shellcheck`, expression syntax). It is not a
project-policy tool. Re-implementing its checks in Rego would duplicate
~3000 lines of Go for zero gain.

The decision is: pin `actionlint` in `Makefile` (same pattern as
`opa`), validate with `make actionlint-check`, install hint in
README, gate `make lint` on its exit code.

**Alternative considered:** wrap actionlint output as JSON, feed into
Rego as facts, write all rules in Rego. Rejected: actionlint's own
findings are already actionable, and the wrap step adds latency + a
fragile JSON contract.

### Decision 2: Two policy files, not one big bundle

`policies/github_actions.rego` and `policies/pyproject.rego` are
distinct files. Each has one `package` declaration and contains
multiple `deny` rules for related concerns.

**Why split**: different fact sources (workflows YAML vs pyproject
TOML), different rule cadences (workflow churn vs dep churn), and
clearer blast radius when a policy needs to be temporarily disabled.

**Why not split further** (one file per rule): five `.rego` files would
fragment shared helpers (e.g. `is_third_party_action`,
`vendor_of(uses)`). One file per surface is the sweet spot.

### Decision 3: extract_facts.py grows two top-level collections

Schema extension:

```jsonc
{
  "functions": [...],       // existing
  "modules": [...],         // existing
  "suppressions": [...],    // existing
  "workflows": [            // NEW
    {
      "file": ".github/workflows/ci.yml",
      "name": "CI",
      "permissions": {"contents": "read"} | null,
      "on": ["push", "pull_request"],
      "jobs": [
        {
          "name": "test",
          "permissions": {...} | null,
          "steps": [
            {
              "uses": "actions/checkout@v4" | null,
              "uses_ref": "v4" | "<40-char-sha>" | null,
              "has_pinned_sha": false,
              "vendor": "actions",
              "with_keys": ["ref", "fetch-depth"]
            }
          ]
        }
      ]
    }
  ],
  "pyproject": {            // NEW
    "dependencies": [
      {"name": "fastapi", "spec": ">=0.115,<0.130", "has_upper_bound": true}
    ],
    "optional_dependencies": {
      "test": [...]
    },
    "build_system_requires": [...]
  }
}
```

`has_pinned_sha` is computed at extract time (`len(ref) == 40 and all
hex`). Vendor is the first `/`-separated component of `uses`. Both
are pre-computed so Rego stays declarative.

**Alternative**: emit raw structures, compute `has_pinned_sha` in
Rego. Rejected: Rego string manipulation is verbose; pre-computing in
Python keeps policies readable.

### Decision 4: vendor allowlist lives in policies/data.json, not Rego

`policies/data.json` already carries per-policy allowlist entries for
body-dup / name-collision. The vendor allowlist for
REGO-GHA-VENDOR-ALLOW is the same shape:

```jsonc
{
  "a2kit": {
    "allowlist": {
      "github_actions_vendor": [
        {"vendor": "actions", "reason": "GitHub official"},
        {"vendor": "astral-sh", "reason": "uv/ruff vendor"}
      ]
    }
  }
}
```

The `reason:` field is required (same enforcement as existing
allowlist entries — `extract_facts.py` fails on missing reason). This
keeps the allowlist auditable.

### Decision 5: pyproject upper-bound applies to runtime deps only

`[project.dependencies]` is gated. `[project.optional-dependencies]`
and the dev group are exempt: optional groups are opt-in by the
consumer; dev deps don't ship. This matches the
`zero-tolerance-runtime-strict-dev` posture documented in
`docs/dev/dependency-policy.md` (if present; otherwise establish it).

**Alternative**: gate all groups. Rejected: noisy; the wins are on
runtime deps that ship to consumers.

### Decision 6: Pipeline order — actionlint before Rego

`make lint` runs `actionlint` first (cheap, parser-level), then
`a2kit lint rego` (which now also reads workflows). Fast-fail on
syntax errors before semantic policies run.

## Risks / Trade-offs

- **Risk:** `actionlint` is a non-Python binary added to bootstrap.
  Mitigation: same `make X-check` pattern as `opa`; bootstrap message
  links to install instructions for macOS/Linux. CI installs via apt.
- **Risk:** YAML parsing in `extract_facts.py` requires `pyyaml`.
  Mitigation: `pyyaml` is already a transitive dep via FastMCP / other
  packages — but if not, add it as a runtime dep of the lint tooling
  (no a2kit package import path picks it up; the script lives in
  `scripts/`).
- **Risk:** First-run noise — existing workflows may not be SHA-pinned.
  Mitigation: audit + fix in-flight as part of this change (probably 1
  workflow file, modest delta). Vendor allowlist seeded from current
  vendors. If unfixable, allowlist entry with `reason: "WIP, scheduled
  for follow-up"` keeps the gate green.
- **Risk:** zizmor superset — if zizmor's catalog grows faster than our
  hand-authored policies, we under-enforce. Mitigation: BACKLOG entry to
  periodically re-audit against zizmor; not a v1 concern.
- **Trade-off:** Extract grows non-Python fact sources, increasing the
  schema surface area. Acceptable — the engine and wire are unchanged;
  schema growth is the explicit way the substrate generalizes.

## Migration

No data migration. Single-pass:

1. Land `actionlint` + extract extension + policies in one branch.
2. Fix any pre-existing workflow / pyproject violations in the same
   commit (or allowlist with reasons).
3. `make lint` becomes the gate from merge onward.

Rollback: revert the commit; substrate is unchanged.
