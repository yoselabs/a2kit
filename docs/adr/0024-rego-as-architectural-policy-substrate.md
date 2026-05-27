---
id: "0024"
status: accepted
date: 2026-05-27
last_reviewed: 2026-05-27
supersedes: []
superseded_by: null
tags: [lint, policy, architecture, tooling]
deciders: [Denis Tomilin]
---

# ADR 0024: Open Policy Agent (Rego) as a2kit's architectural-policy substrate

## Status

Accepted, 2026-05-27. Implemented in change `adopt-rego-policy-layer`.

## Summary

In the context of the 2026-05-27 structural audit (`STRUCTURE_ISSUES.md`)
that catalogued 17 confirmed redundancies and 13 code smells, facing
the fact that the existing `a2kit lint static` AST-rule engine is
verbose for cross-codebase aggregation and that token-based clone
detection (jscpd) catches only a fraction of the audit's findings, we
decided for **Open Policy Agent (Rego)** as a second lint tier
dedicated to architectural invariants — fed by a stable AST-fact
extractor — and against expanding `a2kit lint static` to host
aggregation rules or wiring jscpd as a regression gate, to achieve a
set-oriented, declarative policy substrate that catches the audit's
invariant payload (cross-file body duplication, cross-file
private-helper name collision) and amortizes across additional
non-Python surfaces (GitHub Actions, `pyproject.toml`, OpenSpec shape)
in follow-up changes.

## The problem

Calibration on 2026-05-27 against the 17-entry audit ledger:

- **jscpd** (then configured but unwired) at `min-lines=5 --strict`
  catches ~4/17 audit entries plus 2 new signals. Misses
  *same-name different-body* (R1, R3, R4, R5, R7, R8) and
  *same-shape different-identifiers* (R10, R13) by design — the model
  is token similarity, not invariant.
- **`a2kit lint static`** is per-file, per-pattern. Adding "no two
  private helpers with same name across modules" requires walking the
  whole tree and bucketing — a cross-codebase aggregation that
  doesn't fit the per-file visitor pattern. Writing it natively is
  possible but verbose, and the audit's other invariants (R10's lazy
  `__getattr__` shape, S11's "every transport adapter appends exactly
  one render stage", S1's container concerns) compound the cost.

The category mismatch is structural: `a2kit lint static` polices
**authoring guidance** ("don't write this"), but most of the audit's
findings are **architectural invariants** ("the codebase shall continue
to satisfy property P"). Different tools fit different categories.

## Decision

Adopt Rego as a second tier, distinct from `a2kit lint static`:

```
Tier 1 (existing) — a2kit lint static
  Per-file AST patterns. "You wrote this wrong."
  Example: A2K-NO-DICT-STR-ANY flags dict[str, Any] on a dataclass field.

Tier 2 (this ADR) — a2kit lint rego
  Cross-codebase invariants over extracted AST facts.
  Example: REGO-BODY-DUP flags two functions with matching normalized
  AST hash across files.
```

The pipeline:

```
scripts/extract_facts.py  →  facts JSON
                              {functions, modules, suppressions}
opa eval --bundle policies/  →  deny[] findings
                                 mapped to LintMessage shape
make lint                     →  exit 1 on any deny
```

**Two starter policies** in `policies/` (Phase 1, this change):

- `body_dup.rego` — REGO-BODY-DUP, normalized AST hash matching across
  files, body_stmt_count floor 3.
- `name_collision.rego` — REGO-NAME-COLLISION, cross-file private
  helper name reuse, dunders exempt.

**Allowlist** in `policies/data.json` with required `reason` field per
entry. REGO-* `noqa` directives also require a `-- <reason>` suffix (stricter
than A2K-* convention).

## What this is not

- Not a replacement for `a2kit lint static`. The two tiers coexist;
  Tier-1 rules stay in place. Some Tier-1 rules may migrate to Tier 2
  in follow-ups (per-rule openspec changes) when they fit the
  invariant model better, but no wholesale migration is planned.
- Not a license-checker or SCA tool. SCA stays out of scope.
- Not a runtime policy engine. Rego is used statically here, against
  extracted facts; no policy decisions at runtime.

## Forces

| Force | Pull |
|---|---|
| The audit needs cross-codebase invariants enforced | toward a set-oriented engine |
| `a2kit lint static` already does per-file checks well | toward keeping it as Tier 1 |
| Solo project, minimize toolchain weight | against adding any new tool |
| jscpd was the obvious off-the-shelf choice | against — calibration shows it misses 13/17 |
| OPA is industry-standard for policy-as-code | toward Rego |
| Rego has a learning curve | against — but small for ~5-10 starter policies |
| Future invariants compound (Bundle A, B, follow-ups) | toward an engine that scales |
| The same engine can police GitHub Actions, pyproject.toml | toward Rego (broader payoff) |

## Costs accepted

- **New toolchain dep:** OPA binary (single Go binary, ~60MB, pinned
  in Makefile, `make opa-check` validates version).
- **Learning curve:** Rego is Datalog-derived; team members must learn
  it to author/edit policies. Mitigation: policy file count stays
  small (~5-10 long-term); patterns are stereotyped (`deny contains
  msg if { ... }`); shared helpers in `policies/_helpers.rego`.
- **Two-stage pipeline:** extract → opa eval (vs one stage for native
  AST rules). Adds ~hundreds of ms to `make lint` total runtime.

## jscpd supersession

The `.jscpd.json`, `package.json`, `pnpm-lock.yaml` (the entire Node
toolchain) are removed in the same change. `body_dup.rego` at the
normalized-AST-hash level catches a strict superset of what jscpd
catches at any tuning. Calibration ledger lives in
`STRUCTURE_ISSUES.md` §2.

## Follow-up changes

Filed as `BACKLOG.md` entries (each becomes its own openspec change):

- `policy-bundles-cross-surface` — Phase 1.5; adopt `actionlint`
  (native Go tool for syntax/correctness); author bespoke
  `policies/github_actions.rego` for SHA-pinning, permissions blocks,
  vendor allowlist (reference catalog: `woodruffw/zizmor`'s audit
  list); author bespoke `policies/pyproject.rego` for upper-bound +
  license policy.
- `migrate-a2k-rules-to-rego` — Phase 2 epic; per-rule openspec
  changes, simplest first (`no_dict_str_any`, `metadata_private`,
  `surface_registry`).
- `consolidate-utility-duplications` — Bundle A from
  `STRUCTURE_ISSUES.md`; uses the now-enforced Rego policies as the
  regression gate. Currently 8 audit entries (R2, R7, R8, R9 + 1 new
  body-dup find) are allowlisted in `policies/data.json` with
  `"scheduled for Bundle A"` reasons — that allowlist gets
  drained as Bundle A lands.

## Consequences

- `make lint` gains a Rego policy gate. Adding a new Rego policy is
  ~10-30 lines once `extract_facts.py` surfaces the needed facts.
- Suppression hygiene is stricter for REGO-* than A2K-* (reason
  required); the cost is one extra line per noqa, the benefit is
  every architectural-invariant suppression carries its justification
  inline.
- Foundational `a2kit._ldd_wire` module added to break the layer
  constraint that prevented the naive R6 fix (`packages/context/` is
  L0 and cannot import from `packages/ldd/` directly without closing
  the existing `ldd.ambient → context.request_scope` cycle).
  Foundational placement is the clean precedent extension; recorded
  in `packages/lint/layers.py::FOUNDATIONAL_CORE_MODULES`.

## Related decisions

- ADR 0015 (internal layer DAG) — Tier 2 policies enforce
  layer-adjacent invariants without conflicting with `A2K-LAYER`.
- ADR 0018 (tombstone lifecycle) — REGO-BODY-DUP could in future
  flag tombstone bodies that share shape with active retired methods.
- ADR 0007 (ADR system) — this ADR follows the established
  frontmatter schema.

## References

- `STRUCTURE_ISSUES.md` — the 2026-05-27 audit + jscpd calibration.
- `docs/dev/rego-toolchain.md` — toolchain how-to + policy authoring
  guide.
- `openspec/changes/adopt-rego-policy-layer/` — this change's spec.
- Open Policy Agent: <https://www.openpolicyagent.org/>
- zizmor (GitHub Actions audit catalog, reference for Phase 1.5):
  <https://woodruffw.github.io/zizmor/audits/>
