## Context

a2kit's capability specs in `openspec/specs/` are append-only-ish: each archived change writes or reshapes a spec, but nothing reaches back to retire a requirement when the code it described is later removed. Over ~20 archived changes the rot accumulated. An audit classified all 36 specs and found ~18 drifted or stale. The failure modes cluster:

1. **Removed-symbol "raises with a hint" requirements.** Several specs require that calling a renamed method (`app.singleton`, `has_singleton`, `singletons`, `TestClient.call`) raise a `TypeError` whose message names the replacement. These were honest when written: `App.__getattr__` and `TestClient.__getattr__` intercepted the dead names. The app-runtime internalization removed `App.__getattr__`; the dead names now raise plain `AttributeError`. The spec still promises a hinted `TypeError` the framework no longer delivers.
2. **Specs guarding a retired lint rule.** `core-purity` polices `A2K-CORE-CLEAN`, retired in v0.34 (`src/a2kit/packages/lint/rules/purity.py:7` documents the retirement). `request-scoped-di` references `A2K-DI-CHAIN` / `A2K-DI-PROVIDER`, which were never built. A spec scenario whose `WHEN` invokes a nonexistent rule can never be satisfied.
3. **Phantom files and self-contradiction.** `module-layout-discipline` requires "no underscore-prefixed modules with public symbols" and, four requirements later, mandates that `_verbs.py` and `_verb_validators.py` exist. It also locates `_APP_CTX` in `packages/cli/app_ctx.py` — a file that does not exist.
4. **Museum specs.** `thin-core-surface` was written for a v1.0 surface that never shipped: `uncalled_for`, `Depends`, `dependency_overrides`, `App.use_factory`, `packages/enrichers/`, `packages/middlewares/`, `--format=toon`, core `runner.py` / `cli.py`. The whole capability was superseded.
5. **A three-way contradiction.** Router slug: `core-purity` says verbatim class name, `router-conventions` says strip `Router` suffix and lowercase, the code (`src/a2kit/routers.py`) requires an explicit `slug: str` class attribute and raises if absent. Three artifacts, three answers, at most one can be right.

This change is reconciliation only: it does not redesign any capability. The job is to make every spec match the code that exists today.

## Goals / Non-Goals

**Goals:**

- Every drifted spec's requirement text, symbol names, and scenarios match the current code surface.
- Every stale spec either describes its real successor capability or has its dead requirements REMOVED with `Reason` + `Migration`.
- The router-slug contradiction is resolved to a single answer, consistently, across `core-purity` and `router-conventions`.
- The one genuine live bug (`_lifecycle_helpers.py` naming `app.singleton`) is recorded as an apply-time task.
- After this change, `openspec validate --strict` passes and a reader can trust any reconciled spec.

**Non-Goals:**

- Not authoring new specs for currently-unspecced code (`signature.py`, `metadata.py`, `schema.py`, `exceptions.py`, lint-rule families). Listed as follow-up.
- Not touching `tool-descriptors` — the `remove-dead-surface` change owns it.
- Not changing any runtime behavior except the one error-message fix. This is a documentation-truth change, not a feature change.
- Not deciding the mechanism for deleting a spec directory outright — `add-spec-drift-gate` owns that decision (see Decisions D5).
- Not re-introducing any removed capability (`override`, `_snapshot`/`_restore`, `singleton`, `health_tool=`, `on_startup`) to make a spec true. The spec moves to the code, never the reverse.

## Decisions

### D1. Repair-vs-delete decision criteria

The core judgment of this change is, per requirement: repair it, or REMOVE it. The rule:

- **Repair** when the *capability still exists* and only the *description drifted*. Symptoms: a scenario names a renamed helper (`_infer_format_hint` → `infer_format_hint`), a stale example symbol (`app.singleton` in prose), or a changed signature (`run_checks(app)` → `run_checks(resolver)`). The requirement's intent is still true; the words are stale. Edit the words.
- **REMOVE** when the *capability itself is gone*. Symptoms: the requirement's `WHEN`/`THEN` can never be satisfied because the symbol, method, lint rule, or delivery mechanism was deleted and has no successor. `TestClient.override`, the `A2K-CORE-CLEAN` rule, `App.teardown_failures`, `a2kit.Param`, `App.use_factory` — each is gone with nothing in its place. A REMOVED requirement carries `**Reason**:` (why it is gone) and `**Migration**:` (what a consumer does instead).
- **Rewrite** is repair's heavy form: when the *capability was reshaped into a clearly identifiable successor* (`singleton(...)` → `provide(..., per_call=False)`), the requirement is rewritten to describe the successor rather than deleted. The successor is named in the requirement so the spec still covers that behavior.

The tie-breaker when "repair" and "remove" both look plausible: ask whether a reader who builds against the repaired requirement would write correct code. If the capability has a successor, repair/rewrite to point at it. If not, REMOVE — a deleted requirement is honest; a repaired-to-nothing requirement is not.

### D2. Dead "raises with a hint" requirements are REMOVED, not repaired to `AttributeError`

Tempting alternative: keep the requirement but change `THEN it raises TypeError with a hint` to `THEN it raises AttributeError`. Rejected. The requirement existed to specify a *migration aid* — a deliberately helpful error. Plain `AttributeError` from a missing attribute is not a designed behavior; it is the absence of one. Specifying "accessing a name that does not exist raises `AttributeError`" is specifying Python, not a2kit. These requirements are REMOVED with a `Migration` line naming the current method (`app.provide`, `has_provider`, `providers`, `invoke`). If a hinted-error capability is wanted back, that is a new proposal, not a reconciliation.

### D3. Router slug: the code wins, both specs align to "explicit `slug` required"

`src/a2kit/routers.py` is unambiguous: `slug: str` is a required class attribute, and `Router.__init_subclass__` raises a `TypeError` if a subclass omits it (`"Router subclass ... must define class attribute 'slug: str'"`). There is **no derivation** — not verbatim class name, not suffix-stripping. Both stale specs are wrong in different directions.

Resolution: the code is canonical (AGENTS.md: specs describe code, code does not chase specs). Both specs are reconciled to a single requirement:

> A `Router` subclass MUST declare an explicit non-empty `slug: str` class attribute. The framework MUST NOT derive the slug from the class name (no verbatim fallback, no suffix-strip, no case conversion). A subclass missing `slug` MUST raise `TypeError` at subclass-definition time.

`core-purity`'s "verbatim class-name fallback" requirement is REMOVED (the fallback does not exist). `router-conventions`'s "derives from class name with explicit override" requirement is MODIFIED to the explicit-required form above. After this change the two specs agree with each other and with `routers.py`.

### D4. STALE specs lose dead requirements but keep their true ones; the spec file is not emptied

Even the worst museum spec (`thin-core-surface`) contains a few requirements that are still true (FastMCP is a hard dependency; the thin-core/plugin-package split is real). Reconciliation REMOVEs the dead requirements and keeps or lightly repairs the true ones. The capability folder stays; only the lying requirements leave. This keeps each change's delta legible — a REMOVED block per dead requirement, with `Reason` + `Migration` — and avoids the question of folder deletion entirely for specs that still have a non-empty true core.

`core-purity` is the edge case: if, after removing the `A2K-CORE-CLEAN`-dependent and verbatim-fallback requirements, what remains is genuinely a different capability, the spec is reduced to its honest residue (the introspection-failure and `hasattr`-discipline requirements, which are real and still enforced) rather than deleted. Outright directory deletion is deferred — see D5.

### D5. Spec-directory deletion is deferred to `add-spec-drift-gate`

OpenSpec's delta model expresses removal as `## REMOVED Requirements` inside a `specs/<capability>/spec.md` delta. It is not established that OpenSpec supports *deleting the live `openspec/specs/<capability>/` directory* through a change. If a spec should cease to exist entirely (rather than be reduced to a true residue), that needs a deletion mechanism. The companion change `add-spec-drift-gate` decides that mechanism. This change therefore never relies on directory deletion: every capability here is *reduced* (dead requirements REMOVED, true ones kept), not erased. Should a spec end up with zero true requirements, this change leaves it as an all-REMOVED delta and flags it for `add-spec-drift-gate` to finish.

### D6. The one code edit is recorded as a task, not performed in this artifact set

`_lifecycle_helpers.py` genuinely lies to users at runtime — its `TypeError` messages say `app.singleton(...)`, a method that does not exist. That is a real bug, not just spec drift, so it is in scope. But the instruction for this planning change is planning artifacts only; the edit happens at apply time. It is captured as an explicit task in `tasks.md` under the `app-singletons` group (the capability whose surface the message names) so it is not lost. The `app-singletons` spec delta's `provide`-surface requirement is the spec authority the fix satisfies.

### D7. DRIFTED repairs are scoped to the drifted requirement only

For the 8 DRIFTED specs the temptation is to "tidy while here." Resisted. A DRIFTED spec is mostly correct; the change touches only the requirement(s) and scenario(s) with stale symbols. `mcp-context-passthrough` is 545 lines — the delta MODIFIES only the two requirements whose scenarios name `on_startup` / `app.singleton`, not the other dozen. Narrow deltas keep review tractable and keep the change's blast radius honest.

## Risks / Trade-offs

- **A reconciled spec could still miss a drift the audit did not catch.** → The audit's dead-symbol worklist is enumerated by the `add-spec-drift-gate` change's gate; once that gate is live it will flag any residual drift in CI. This change clears the known worklist; the gate catches the rest going forward. Stating the dependency explicitly is the mitigation.
- **Removing a requirement loses the historical record of why a capability existed.** → OpenSpec archives the change; the REMOVED block with `Reason` + `Migration` is itself the record. The decision log (ADRs) carries the deeper "why" for the original removals.
- **Resolving the router-slug contradiction to the code may surprise a reader who trusted `router-conventions`.** → That reader was already writing broken code (the derivation does not run; their slug-less router crashes at subclass definition). Aligning the spec to the code converts a silent trap into a documented requirement. The MODIFIED block names the prior wrong behavior so the diff is self-explaining.
- **Large DRIFTED specs (`mcp-context-passthrough`, `operational-contracts`) risk an incomplete repair if a stale symbol is missed.** → Each was grepped for the specific dead symbols (`on_startup`, `on_shutdown`, `app.singleton`, `health_tool`) before authoring; the delta MODIFIES exactly the matched requirements. The grep is the checklist.
- **Validation strain.** This change ships 17 delta files. → If `openspec validate --strict` strains, the 9 STALE deltas are authored first and most carefully (they carry the REMOVED blocks that need `Reason`/`Migration`); the 8 DRIFTED deltas are smaller MODIFIED-only edits. All 17 are attempted; STALE is the priority if a cut is forced.

## Migration Plan

1. Land `add-spec-drift-gate` first (provides the dead-symbol worklist and the spec-deletion mechanism). This change declares the dependency; it can be authored in parallel but archives after the gate.
2. Apply this change: write the 17 reconciled `openspec/specs/<name>/spec.md` files from the deltas, and make the single `_lifecycle_helpers.py` edit.
3. Run `openspec validate --strict`, `make check`, and the `add-spec-drift-gate` gate — the gate's dead-symbol worklist should report zero findings against the reconciled specs.
4. Archive.

Rollback: this change edits specs (recoverable from git) and one error message (cosmetic). There is no runtime-behavior rollback surface.

## Open Questions

- Does any reconciled spec end up with zero true requirements (an all-REMOVED delta)? If so it is handed to `add-spec-drift-gate` for directory deletion. Current assessment: `thin-core-surface` and `core-purity` are the candidates; both retain a true residue, so directory deletion is expected to be unnecessary — but `add-spec-drift-gate` makes the final call.
- Should `app-singletons` be renamed to `provide-api` (the capability name is itself stale)? Deferred: renaming a capability folder is friction for no consumer-visible gain, and OpenSpec rename mechanics are out of this change's scope. Noted as organizational debt.
