## Context

The `spec-drift-gate` capability (`tests/test_spec_symbol_drift.py`)
resolves every backtick-quoted a2kit symbol in `openspec/specs/*/spec.md`
against the live surface. It landed green by grandfathering known drift
into an allowlist, each entry tagged `# reconcile:` with the owning
spec(s). `reconcile-stale-specs` cut that allowlist from ~65 to 38
entries; this change clears the remaining 38.

The 38 residual entries fall into two populations:

1. **Reconciled specs that still cite removed names.** `reconcile-stale-specs`
   touched these specs but its delta bodies cite removed symbols to
   *document* the migration — e.g. `app-singletons` has a scenario
   "`app.singleton` is a missing attribute". ADR 0018 D7.2: a living
   capability spec describes the *current* surface; a removed-surface
   citation is drift by construction.
2. **Specs never in `reconcile-stale-specs`' scope.** Seven specs —
   `otel-adapter`, `di-conditional-injection`, `lazy-init-resources`,
   `verb-decorators`, `test-container-peek`, `di-scope-cleanup-stack`,
   `app-builder-runtime` — were outside that change's 17-delta worklist
   and were never reconciled at all.

This is a planning artifact set. The implementation, when it lands, must
keep `make check` green: the gate is in `make lint`, so every `# reconcile:`
entry removed from the allowlist must be matched by the owning spec no
longer citing that symbol.

## Goals / Non-Goals

**Goals:**

- Every `# reconcile:` entry in the gate's allowlist is removed; the
  gate runs green with only tombstone-target and illustrative entries.
- Each reconciled spec describes only the live `a2kit` surface — no
  backtick citation of a removed name, not even to document its
  absence.
- The superseded `app-builder-runtime` capability spec is deleted from
  the spec tree, its history preserved in the OpenSpec archive.

**Non-Goals:**

- No code change. `src/a2kit/` is untouched; this is a spec-tree and
  gate-allowlist change only.
- No change to the `spec-drift-gate` capability's requirements. The
  allowlist *mechanism* is unchanged; only its grandfathered *contents*
  shrink to empty. The gate's own spec needs no delta.
- No new automated gate, no extension of the gate to docs or AGENTS.md
  (that remains a separate possible follow-up).
- No re-litigation of the reconciled requirement *bodies* from
  `reconcile-stale-specs` beyond removing dead-name citations.

## Decisions

### D1. Dead-name citations are rewritten, not allowlisted forever

A spec sentence like "`app.singleton` raises `AttributeError`" is the
ADR 0018 D7.2 anti-pattern: a living spec asserting removed-surface
behaviour. The fix is not a permanent allowlist entry — it is to delete
or rewrite the sentence so the spec describes only what `a2kit` does
today. Where the citation carried real intent (a migration note), that
intent moves to the change record / `CHANGELOG.md`, which is where
migration history belongs; the living spec keeps only the live surface.

### D2. `app-builder-runtime` is deleted, not repaired

The `app-builder-runtime` capability described the short-lived
`AppBuilder` / sealed-`App` two-type split (ADR 0016), superseded the
same day by the one-`App` collapse (ADR 0017). Per ADR 0018 D7.3 a
superseded capability spec is deleted from `openspec/specs/`, not kept
as a husk of `REMOVED` requirements.

OpenSpec deltas cannot express this: a `## REMOVED Requirements` block
covering every requirement rebuilds the spec to zero requirements, and
the archive validator rejects an empty spec ("Spec must have at least
one requirement"). So the deletion is **not** a delta — it is a direct
removal of the `openspec/specs/app-builder-runtime/` directory, done as
an implementation task. The capability's history is preserved in git
and in the archived `split-app-builder-runtime` change; the one-`App`
surface that replaced it is owned by the `app-lifecycle` and
`app-singletons` capabilities.

### D3. The seven unscoped specs are reconciled the same way as the rest

`otel-adapter`, `di-conditional-injection`, `lazy-init-resources`,
`verb-decorators`, `test-container-peek`, and `di-scope-cleanup-stack`
were never in `reconcile-stale-specs`' scope. They are not special —
each gets a delta that rewrites its dead-symbol citations to the live
surface, exactly as the reconciled specs do. `app-builder-runtime` is
the one exception (D2: deleted).

### D4. The allowlist is emptied in lockstep with the spec deltas

`tests/test_spec_symbol_drift.py`'s allowlist has three groups:
tombstone-migration targets, illustrative placeholders, and
`# reconcile:` grandfathered drift. This change removes the entire
grandfathered group. The implementation removes an allowlist entry only
after the owning spec stops citing that symbol — the gate is the
verification. The two remaining groups stay: tombstone targets
(`a2kit.AppBuilder`, `a2kit.tool`) are deliberately-removed names a
spec may cite in a `REMOVED` requirement's migration line, and the
illustrative placeholders (`App.method`, …) are pattern-description
metavariables, not drift.

### D5. Per-spec verification is the gate itself

There is no separate verification step per spec. The gate
(`test_all_spec_symbols_resolve_in_live_code`) is run after each delta
batch is applied and each allowlist group is trimmed; a green gate with
an empty grandfathered section is the done condition. `make check`
(which runs the gate via `make lint`) is the final gate.

## Risks / Trade-offs

- **A dead-name citation carried load-bearing migration intent** →
  Mitigation: D1 — the intent moves to `CHANGELOG.md` / the change
  record, not lost, just relocated to where migration history belongs.
- **Deleting `app-builder-runtime` loses the AppBuilder rationale** →
  Mitigation: the rationale lives in ADR 0016 (status `superseded`) and
  the OpenSpec archive of the `split-app-builder-runtime` change. The
  spec tree is a catalogue of today; the archive is the history.
- **A reconciled spec's residue is too thin to stand alone** → some
  specs may shrink to one or two requirements once dead citations go.
  Mitigation: a thin-but-true spec is still correct; a directory-level
  "is this still its own capability?" judgement is out of scope here
  and noted as a possible future consolidation, not forced now.
- **New drift lands between this proposal and its apply** → Mitigation:
  the gate is already in `make lint`; any *new* drift fails CI
  immediately, so the residual set this change targets cannot silently
  grow.
