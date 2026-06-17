# Rego policy toolchain

a2kit uses **Open Policy Agent (OPA)** as the policy substrate for
codebase-wide architectural invariants. This is distinct from the
existing `a2kit lint static` rule engine — they serve different tiers:

| Tier | Tool | Catches | Example |
|---|---|---|---|
| **Authoring guidance** | `a2kit lint static` (Python AST rules) | "you wrote this wrong" — per-file, per-pattern | `A2K-NO-DICT-STR-ANY` on a `dict[str, Any]` field |
| **Architectural invariants** | `a2kit lint rego` (OPA + Rego) | "the codebase shall continue to satisfy property P" — cross-file, set-oriented | `REGO-BODY-DUP` flags two functions with matching normalized AST hash across files |

## Why Rego

The 2026-05-27 structural audit (`STRUCTURE_ISSUES.md`) found 17
redundancies and 13 smells, most of which are *invariants* about the
codebase's shape, not authoring mistakes. Examples:

- **R6** — `_cap_text` / `_format_kv` / `format_condensed_line` duplicated
  across `packages/log/wire.py` and `packages/context/stderr.py`.
  Drift here is a wire-format bug per the log invariant.
- **R1** — two `async def _call` helpers with identical bodies in
  different modules of `packages/dispatch/`.
- **R10** — lazy `__getattr__` pattern hand-rolled across 7 modules.

Calibration runs found:

- **jscpd** catches ~4/17 entries at the body-similarity level but
  fundamentally misses *same-name different-body* and *same-shape
  different-identifiers*. Now superseded by `body_dup.rego`'s
  normalized AST hash, which catches a strict superset with no
  false positives.
- The existing AST-rule engine is verbose for cross-codebase
  aggregation. Rego's set-oriented model expresses "no two with
  the same X" in 10 lines.

## What's where

```
scripts/extract_facts.py       Walks src/**/*.py + .github/workflows/*.yml
                               + pyproject.toml, emits curated JSON
                               (functions, modules, suppressions,
                               workflows, pyproject). Pure function of
                               input tree + repo root.
policies/                      Rego policy bundle (.rego files).
  body_dup.rego                Cross-file body duplication.
  name_collision.rego          Cross-file private-helper name reuse.
  github_actions.rego          REGO-GHA-PIN-SHA / -PERMISSIONS /
                               -VENDOR-ALLOW supply-chain hygiene over
                               input.workflows.
  pyproject.rego               REGO-PYPROJECT-UPPER-BOUND on runtime
                               deps in input.pyproject.dependencies.
  data.json                    Per-policy allowlist entries with
                               required `reason` field, nested under
                               {a2kit: {allowlist: {body_dup: [...],
                               name_collision: [...],
                               github_actions_vendor: [...],
                               github_actions_vendor_unpinned: [...],
                               pyproject_upper_bound: [...]}}}.
                               Loaded into `data.a2kit.allowlist` when
                               the bundle is evaluated.
src/a2kit/packages/lint/
  rego.py                      `a2kit lint rego` subcommand wrapper.
                               Pipeline: extract → opa eval → emit
                               findings as the existing LintMessage
                               shape.
```

## Install

Both `opa` and `actionlint` are pinned in the `Makefile`. The
`bootstrap:` target verifies both; install yourself first.

**macOS:**

```bash
brew install opa actionlint
```

**Linux:**

```bash
curl -L -o /usr/local/bin/opa https://openpolicyagent.org/downloads/v1.16.2/opa_linux_amd64_static
chmod +x /usr/local/bin/opa
bash <(curl -L https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) 1.7.12 /usr/local/bin
```

Verify: `make opa-check` and `make actionlint-check`.

## Authoring a new policy

1. Identify the fact you need to express. If `scripts/extract_facts.py`
   already emits it (run `python scripts/extract_facts.py --schema`
   to inspect the contract), proceed. If not, extend the extractor
   first (small, focused change).
2. Author the policy in `policies/<name>.rego`:

   ```rego
   package a2kit
   import future.keywords

   deny contains msg if {
     # set-oriented aggregation here
     msg := sprintf("...", [...])
   }
   ```

3. Allowlist entries (if any) live under `policies/data.json` at
   `a2kit.allowlist.<policy_name>`. Each entry SHALL include
   a non-empty `reason` field; allowlist load fails otherwise.
4. Add a capability test under `tests/capabilities/rego_policy_layer/`
   exercising the policy against a fixture.
5. Wire the rule ID into `src/a2kit/packages/lint/rego.py` if needed
   (the wrapper auto-discovers `deny` from the bundle; manual
   wiring is only required for non-`deny` rules).

## Suppressing a finding

For genuinely intentional convergence, add an inline noqa:

```python
# noqa: REGO-BODY-DUP -- intentional parallel impl; see ADR-NNNN
```

The grammar matches `packages/lint/static.py:parse_noqa`: separator
is ` -- ` (space-dash-dash-space), reason is free text after.

**Important:** REGO-* rules require a reason. A bare `# noqa:
REGO-BODY-DUP` (no ` -- ` suffix) is a hard error — `extract_facts.py`
fails. This is stricter than A2K-* rules, where reasons are
conventional. Rego policies enforce architectural invariants;
every suppression must be justified.

For broader exemptions (a class of names always exempt), use
`policies/data.json` instead — it's reviewable and discoverable.

## Debugging a `deny`

When a policy fires unexpectedly:

```sh
# 1. See the raw extracted facts for the offending file
python scripts/extract_facts.py | jq '.functions[] | select(.file | contains("path/to/file.py"))'

# 2. Trace the policy evaluation
opa eval --bundle policies/ --input <(python scripts/extract_facts.py) \
  --format pretty --explain notes \
  'data.a2kit.deny'

# 3. Test a single policy in isolation against a fixture
opa eval --bundle policies/body_dup.rego --input <(cat fixture-facts.json) \
  'data.a2kit.deny'
```

The Rego Playground (https://play.openpolicyagent.org/) is a fast
way to iterate on a policy without local extract runs — paste in a
hand-crafted fact JSON and the policy text.

## Cross-surface policies

The substrate is fact-source-agnostic. Three policy domains live under
the same engine + wrapper:

| Domain | Fact source | Policies |
|---|---|---|
| Python code | `src/**/*.py` (AST) | `body_dup.rego`, `name_collision.rego` |
| GitHub Actions | `.github/workflows/*.yml` (YAML) | `github_actions.rego` (3 rules: PIN-SHA, PERMISSIONS, VENDOR-ALLOW) |
| Package metadata | `pyproject.toml` (TOML) | `pyproject.rego` (UPPER-BOUND on `[project.dependencies]`) |

Adding a domain is mechanical:

1. Extend `scripts/extract_facts.py` with a new top-level collection
   (e.g. `dockerfiles`, `precommit_hooks`).
2. Pre-compute derived booleans in the extractor so the Rego stays
   declarative.
3. Author `policies/<domain>.rego`; if the rule needs an allowlist,
   add a section to `policies/data.json` under
   `a2kit.allowlist.<policy_name>` (entries must carry `reason`).
4. Add capability tests under `tests/capabilities/rego_policy_layer/`.

The `actionlint` binary is wired into `make lint` alongside (not
inside) the Rego layer — it's a parser/correctness gate, separate
from project-policy. Same install + version-pin pattern as `opa`.

See ADR 0026 for the cross-surface design rationale.

## jscpd supersession

The project previously declared `jscpd` in `package.json` (never
wired into `make lint`). Calibration on 2026-05-27 against the
17-entry audit ledger showed `body_dup.rego` at the normalized-AST-hash
level catches a strict superset of what jscpd at any tuning catches,
with no false positives. `jscpd` and the entire Node toolchain were
removed in change `adopt-rego-policy-layer`. See
`STRUCTURE_ISSUES.md` §2 for the calibration ledger.
