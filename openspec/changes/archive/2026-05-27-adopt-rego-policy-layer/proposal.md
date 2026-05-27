## Why

The 2026-05-27 structural audit (`STRUCTURE_ISSUES.md`) catalogued 17
confirmed redundancies and 13 code smells. Calibration runs against
the existing toolchain found:

- **jscpd** (currently configured but never wired into `make lint`) at
  min-lines=5 strict catches ~4 of 17 audit entries plus 2 new signals
  the audit missed — but its body-similarity model fundamentally
  misses *same-name different-body* (R1, R3, R4, R5, R7, R8) and
  *same-shape different-identifiers* (R10, parts of R13).
- The existing `a2kit lint static` AST-rule engine (15+ `A2K-*` rules)
  is well-suited to per-file pattern checks but verbose for
  cross-codebase aggregation — "no two private helpers with the same
  name across modules" requires walking the whole tree and bucketing,
  which doesn't fit the per-file visitor pattern.
- More importantly: most of the audit's findings are not "authoring
  mistakes" (which `a2kit lint` polices well) but *architectural
  invariants* — "the codebase shall continue to satisfy property P."
  Examples: R6 (LDD wire-format functions must produce identical
  output — drift is a wire-shape bug), S11 (every transport adapter
  appends exactly one render stage), R10 (lazy `__getattr__` pattern
  should use one canonical registry).

These are policy claims about the codebase, not lint findings. The
right tool family is **policy-as-code** (Open Policy Agent / Rego):
set-oriented, declarative, aggregation-native, with a clean
data/policy separation. Once an AST-fact extractor exists, each new
invariant is ~10-30 lines of Rego instead of a new AST-visitor file.

The investment also amortizes beyond Python source — GitHub Actions
supply-chain hardening, `pyproject.toml` dependency policy, and
OpenSpec shape are all natural Rego workloads. A repo-surface survey
on 2026-05-27 found **no plug-and-play OSS Rego bundles apply
directly** (Rego ecosystem clustered around k8s / Terraform / Docker;
this repo has none of those). What does transfer: patterns and
idioms from `open-policy-agent/library` and `gatekeeper-library`
(deny aggregation, helpers, test conventions), and the rule catalog
from `woodruffw/zizmor` (GitHub Actions security audits) re-encoded
as Rego. For GitHub Actions specifically, **`actionlint` is the
right tool for syntax/correctness** (community converged on it, not
Rego); Rego sits on top for project policy (SHA-pinning, vendor
allowlist, permissions blocks). Phase 1 (this change) lands the
foundation; Phase 1.5 (separate fast-follow) adopts actionlint and
authors bespoke cross-surface policies for Actions and pyproject.

**R6 specifically:** `_cap_text` / `_format_kv` / `format_ldd_line`
duplicate across `packages/ldd/wire.py` and `packages/context/stderr.py`
with `TEXT_CAP` vs `_TEXT_CAP` divergence. Per the LDD wire-format
invariant (auto-memory `feedback_a2kit_ldd_wire_format`), drift here
is a bug. This change MUST close R6 as part of its acceptance — the
body-dup policy catches it on the first run.

## What Changes

- New private framework module
  `scripts/extract_facts.py` — walks `src/**/*.py`, emits curated
  fact JSON: `{functions: [...], classes: [...], modules: [...],
  suppressions: [...]}`. Each function carries `ast_hash_normalized`
  (identifiers + literals stubbed, structure preserved) for body-dup
  detection. Deliberately small projection, not raw AST.
- New `policies/` directory at repo root holding Rego bundles.
- Two starter policies:
  - `policies/body_dup.rego` — flags any two functions with matching
    `ast_hash_normalized` from different files, modulo allowlist.
    **Closes R2, R6, R13 + the DI param-introspection bonus find from
    calibration.**
  - `policies/name_collision.rego` — flags any two `_`-prefixed
    (non-dunder) function names appearing in different files, modulo
    allowlist. **Closes R1, R3, R4, R5, R8 + R7 partial + R9.**
- New private framework module `src/a2kit/packages/lint/rego.py` —
  thin wrapper invoked from `a2kit lint` CLI: runs extract, calls
  `opa eval`, formats findings as the existing `A2K-*` finding shape,
  threads `--noqa` suppression filtering.
- `noqa` preservation contract: `extract_facts.py` emits every
  `# noqa: REGO-* -- <reason>` directive as a suppression fact;
  every Rego policy SHALL filter its `deny` set against the
  suppression set before emitting. Grammar matches existing
  `packages/lint/static.py:parse_noqa` (separator is ` -- `, reason
  is free text after; see commit `83819db`). REGO-* rules upgrade
  the convention to *required* — a `# noqa: REGO-*` without a
  ` -- ` reason is a hard error from `extract_facts.py`.
- OPA binary: documented in bootstrap as `brew install opa` (Linux:
  `curl` from official release). Not vendored — single Go binary,
  reproducible, ~60MB; vendoring is a separate decision if CI
  cold-cache matters.
- `make lint` gains one step: `uv run a2kit lint rego` (which calls
  the wrapper). Native `a2kit lint static` keeps running unchanged.
- `.jscpd.json` and `package.json`'s `lint:jscpd` script are
  **removed** — body-dup policy supersedes (calibration showed jscpd
  catches a strict subset of what the normalized AST hash catches).
- Capability spec `rego-policy-layer` documents the
  extract-facts + Rego-policy + noqa-filter contract.
- BACKLOG entries filed for follow-up changes:
  - `policy-bundles-cross-surface` (Phase 1.5 — adopt `actionlint`
    as native tool for GH Actions correctness; author bespoke
    `policies/github_actions.rego` for SHA-pinning + permissions +
    vendor allowlist using zizmor's audit catalog as reference;
    author bespoke `policies/pyproject.rego` for dep upper-bound +
    license policy)
  - `migrate-a2k-rules-to-rego` (Phase 2 — per-rule, iterative;
    starts with `no_dict_str_any`, `metadata_private`)
  - `rego-policy-r10-lazy-getattr` (uses the same body-dup engine
    once the canonical lazy-attr helper exists)

## Capabilities

### New Capabilities
- `rego-policy-layer` — codebase-facts extraction shape +
  Rego policy authoring contract + `noqa --reason` suppression
  invariant + `a2kit lint rego` integration point.

## Impact

- Affected code: new `scripts/extract_facts.py` (~300-500 LOC),
  new `policies/` directory (2 policy files + allowlist data file),
  new `src/a2kit/packages/lint/rego.py` (~100 LOC wrapper +
  finding-shape adapter), 1 line in `Makefile` `lint:` target,
  3 lines in `Makefile` `bootstrap:` target.
- Removed: `.jscpd.json`, `package.json`, `pnpm-lock.yaml` (jscpd
  superseded; no other Node tooling currently lives here).
- New dev-time toolchain dep: `opa` binary (documented, not vendored).
- Acceptance: `make lint` fails until R6 (LDD formatter dup) is
  resolved by collapsing `packages/context/stderr.py:337` to import
  from `packages/ldd/wire.py:21`. That resolution lands in this same
  change as a worked-example of how Rego findings translate to fixes.
- No public API change. The `a2kit lint` CLI gains the `rego`
  subcommand; `a2kit lint static` is unchanged.
- Migration of existing `A2K-*` rules is **explicitly out of scope** —
  Phase 2+ work, per-rule openspec changes.

## Open questions

1. **OPA binary distribution.** Bootstrap docs vs vendored binary.
   Recommendation: documented install for now (single line in
   `bootstrap:`); revisit if CI cold-cache time matters.
2. **Allowlist file format.** `.rego` data file vs `.json` data file.
   Both work with `opa eval --data`; `.json` is friendlier to non-Rego
   contributors who just want to add an exemption. Recommendation:
   `policies/allowlist.json` with required `reason` field per entry,
   shaped like the `A2K-*` `--reason` grammar.
3. **Hash normalization aggressiveness.** Should `ast_hash_normalized`
   also strip type annotations? Calibration says yes (R6 differs only
   in identifier names, and type annotations are part of "shape" the
   policy should treat as material). Defer to design.md if surprising
   matches surface during implementation.
