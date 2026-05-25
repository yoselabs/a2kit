---
id: "0023"
status: accepted
date: 2026-05-25
last_reviewed: 2026-05-25
supersedes: []
superseded_by: null
tags: [surface, auth, tier-1, principal, governance]
deciders: [Denis Tomilin]
---

# ADR 0023: `Principal` is Tier 1

## Status

Accepted, 2026-05-25.

## Summary

In the context of ADR 0004's Tier 1 promotion gate — which requires a
new ADR for every name added to the `a2kit.*` front door — facing the
fact that `Principal` was added to `_LAZY_ATTRS` during the auth wave
(`add-auth` change, archived 2026-05-24) without the paired ADR that
0004 mandates, and surfaced as the headline finding of the
coherence-audit dispatched on 2026-05-25, we decided to **retroactively
ratify `Principal`'s Tier 1 placement** and against demoting it to a
Tier 2 `a2kit.<domain>` module, to achieve a front-door surface that
matches how authorized tool authors actually write their tool
signatures (`async def me(*, principal: Principal) -> ...`), accepting
that the historical addition bypassed the ADR gate (which the new
snapshot suite, landed in change `tier-surface-snapshot-tests`,
prevents from recurring).

## The problem

`Principal` is the type a tool author writes as a function-parameter
annotation to receive the authenticated subject:

```python
@app.read
async def me(*, principal: Principal) -> dict:
    return {"subject": principal.subject, "scopes": list(principal.scopes)}
```

Per the `principal-propagation` capability spec, the framework resolves
this dependency through the per-call DI scope: the substrate adapter
(MCP `PrincipalMiddleware`, FastAPI `Security` guard) writes a
`Principal` into the scope before tool body dispatch; the body declares
`principal: Principal` and receives it via type-driven resolution. No
explicit registration is required of the author.

This pattern is exactly the 95% verb-authoring case ADR 0004
enumerates. The friction of importing from a longer path
(`from a2kit.packages.context import Principal`) lands on every author
who writes any authorized tool. ADR 0020 (multi-surface authoring) and
ADR 0010 (auth-MCP-mode-only) collectively normalize "every remote MCP
tool is potentially authorized."

The historical slip: `_LAZY_ATTRS["Principal"]` was added in the
`add-auth` change without a paired ADR. ADR 0004 explicitly forbids
this. The coherence audit dispatched on 2026-05-25 surfaced the
violation; this ADR closes it.

## What we considered (and why this one)

### Option 1: Demote `Principal` to a new Tier 2 `a2kit.auth` module

Move the symbol out of `_LAZY_ATTRS` and create
`src/a2kit/auth.py` as a thin re-export from `a2kit.packages.context`
(and/or `a2kit.packages.auth`). Authors write
`from a2kit.auth import Principal`.

Rejected. Tier 2 fits an audience that is "larger than specialized
consumer, smaller than every tool author." `Principal` is consumed by
every authorized tool body — the audience is the same shape as the
audience for `read` / `write` / `list_` themselves (every tool author),
just gated on whether the tool is authorized. The Tier-2 placement
would carry the wrong signal ("specialized") for the actual usage.

### Option 2: Keep `Principal` at Tier 3 only

Remove from `_LAZY_ATTRS`; authors import
`from a2kit.packages.context import Principal`.

Rejected. The longer path is the deliberate ADR 0004 signal for
"outside the default audience." Authorized tool bodies are inside the
default audience; the signal would be misleading. Two-segment imports
for the symbol an author types in every authorized tool signature is
the friction this tiering is meant to remove.

### Option 3: Promote `Principal` to Tier 1 (chosen)

`Principal` stays in `_LAZY_ATTRS`. ADR 0004's Tier 1 enumeration is
amended to include it. The snapshot suite landed in
`tier-surface-snapshot-tests` enforces that future surface changes go
through the ADR-paired diff workflow.

Chosen because:

- The usage pattern matches the 95% audience definition. Tool bodies
  type-annotate `principal: Principal` exactly the way they
  type-annotate `ctx: ToolContext` (already Tier 1) or use `@app.read`
  (already Tier 1).
- The companion ADRs in the auth wave (0010, 0020) and the
  `principal-propagation` spec all assume DI-driven resolution at the
  body, which means the type is a first-class authoring surface.
- The snapshot enforcement now closes the gate that allowed the
  original slip; retroactive ratification is durable.

### Option 4: Block on a stronger audience signal first

Wait until two or more downstream consumers (a2atlassian, a2db,
a2web, a2sdlc) have shipped authorized tools and publish usage data
before deciding.

Rejected. Three pieces of evidence already point the same way: ADR
0020's multi-surface authoring model, ADR 0010's MCP-mode auth scope,
and the `principal-propagation` spec contract. Waiting for downstream
adoption to ratify a decision the framework's own contracts already
imply just defers the snapshot gate's first hard test.

## The decision

`Principal` is Tier 1, retroactively ratified. The Tier-1 enumeration
in ADR 0004 is updated to list it alongside the other authoring
primitives. The `_LAZY_ATTRS` entry stays as-is.

The snapshot tests under `tests/surface/` now enforce ADR 0004's
"promotion requires ADR" rule mechanically: any future change to the
`a2kit.*` public surface produces a checked-in expectation diff
alongside the ADR amendment, in the same commit.

## Consequences

### Positive

- Authorized-tool authors keep the short import
  (`from a2kit import Principal`), matching the pattern they already
  use for `App`, `read`, `ToolContext`.
- The ADR-paired-with-snapshot-diff workflow now has a worked example
  it can cite for future promotions.
- The historical violation is resolved without code churn: only this
  ADR plus the Tier-1 list amendment in ADR 0004.

### Negative

- The Tier-1 surface grows by one. ADR 0004's "Tier 1 is for names
  every tool author uses" claim now includes a name many authors will
  not use (unauthorized tools never need `Principal`). The
  justification: the *type itself* is what unauthorized authors skip;
  authorized authors are the 95% case *for authorized tools*, and the
  authoring ergonomics of authorized tools should match the unauthorized
  baseline.
- This ADR sets a precedent for retroactive ratification. To avoid the
  pattern becoming routine, the snapshot suite is now the enforcement
  mechanism that catches the next slip *before* a retroactive ADR is
  needed.

## References

- ADR 0004 — `Principal` is now listed in the Tier 1 enumeration.
- ADR 0010 — Authentication is an MCP-mode concern; the source of
  the wire-level mechanism that produces `Principal`.
- ADR 0020 — Multi-surface authoring; every typed parameter is a
  first-class authoring surface.
- `openspec/specs/principal-propagation/spec.md` — the contract that
  makes `principal: Principal` a typed dependency resolved via DI.
- `openspec/specs/principal-type/spec.md` — the `Principal` type
  definition.
- `tests/surface/` — the snapshot suite that prevents the next
  Tier-1 slip.
- `src/a2kit/__init__.py` — `_LAZY_ATTRS["Principal"]` entry.
- Coherence audit, 2026-05-25 (`Researches/132-a2kit-structural-audit/`
  or session memory) — the audit that surfaced the original slip.
