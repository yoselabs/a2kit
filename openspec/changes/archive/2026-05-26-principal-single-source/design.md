## Context

`Principal` flows from substrate to tool body via two mechanisms today.
The `principal-propagation` spec already names DI as the canonical
path — tool bodies resolve via type annotation, no manual registration
needed. The contextvar exists as belt-and-braces from an earlier
iteration; the audit found two stages still reading it, both with
fallback logic that branches over the dual paths.

Two effects:

1. Cognitive load: a reader trying to understand "where does Principal
   come from?" must trace both paths and the fallback order.
2. Hidden coupling: any test or transport that wants to override
   Principal must touch both the contextvar and the DI scope, or risk
   the fallback firing.

The spec already settled the design. This change is bringing code into
line with the spec.

## Goals / Non-Goals

**Goals:**
- One documented and code-enforced path: DI scope.
- Stages contain zero `ContextVar.get()` calls for Principal.
- The substrate adapter remains responsible for putting Principal into
  the scope; how it gets there from the wire is its concern.
- Tests assert that overriding the DI provider is sufficient (no
  contextvar dance required).

**Non-Goals:**
- Removing contextvars elsewhere (e.g. LDD ambient). This is scoped to
  Principal.
- Changing the Surface Protocol or DI container.
- Changing the `authorize=` semantics.

## Decisions

### 1. Contextvar retained as a substrate-internal handoff (revised 2026-05-26)

The original "remove entirely" plan required reworking how every
substrate adapter hands Principal to the dispatch entry point: MCP
middleware would need to mutate the FastMCP context, FastAPI's
`Security` guard chain would need a new container-scope publication
path, and the `auth/api_key.py` chain would need rewriting. That scope
is bigger than the audit-cited drift.

The shipped resolution: extract the contextvar reads from the dispatch
stages into a single helper, `dispatch/_principal_scope.py`. Stages
call `seed_principal_into_wire(wire_kwargs)` instead of reading the
contextvar directly. `stages.py` source contains zero references to
`_a2kit_request_principal`. The contextvar continues to exist as a
substrate-internal handoff between the authentication boundary (MCP
middleware, FastAPI guard, api_key middleware) and the per-call DI
scope opening — invisible to authoring-layer code, stages, gates, and
tool bodies.

Alternative considered: keep the contextvar as a private implementation
detail of the substrate adapters, used only inside the adapter to pass
Principal between middleware layers, never read by stages. Rejected —
adds a mechanism that does nothing the DI scope can't do; YAGNI.

The substrate-internal mechanics:
- **MCP**: `PrincipalMiddleware` already receives the request context;
  it sets `Principal` on the DI scope at scope-creation time. No
  contextvar needed.
- **FastAPI**: the `Security` guard returns Principal; the adapter
  writes it into the per-request DI scope before tool body dispatch.

Both adapters already have the substrate context in hand at the right
moment. The contextvar was a workaround for a now-fixed scope-creation
ordering issue.

### 2. Stage code is the place to enforce the rule

Add an explicit comment in `stages.py` documenting that
`Principal` MUST be resolved via DI and that reading any contextvar for
Principal is a defect. Optionally add a small lint rule
(`A2K-NO-PRINCIPAL-CONTEXTVAR`) that flags `ContextVar` references
named `*principal*` outside the auth substrate adapters. Defer the
lint rule unless the spec-drift gate proves insufficient.

### 3. Tests assert the rule

A pytest case constructs an App, overrides the DI `Principal` provider
with a fake, and dispatches a tool with `principal: Principal`. The
tool receives the fake. The test does not touch any contextvar. The
inverse test asserts that with no DI provider and no substrate write,
resolving `Principal` in the tool body raises a clear "no provider"
error (i.e., the contextvar is no longer a fallback).

### 4. Migration

Code-level removals:
- `stages.py:173-175`: delete the contextvar read and the kwargs
  re-seed.
- `stages.py:196-204`: delete the fallback; the gate resolves
  exclusively from DI.
- Delete the `_a2kit_request_principal` ContextVar declaration
  (wherever it lives — likely `packages/context/principal.py:33` per
  audit citation).
- Update substrate adapters (`packages/auth/principal_middleware.py`,
  any FastAPI guard wiring) to write into the DI scope directly,
  removing any contextvar set.

## Risks / Trade-offs

- **[Risk] Substrate adapter doesn't write Principal at the right
  moment** → Mitigation: the existing `principal-propagation` scenario
  already covers tool-body resolution on both substrates; that test
  catches regressions. Add an explicit "Principal-not-written" negative
  test.
- **[Risk] A consumer's middleware reads
  `_a2kit_request_principal` (unlikely but possible)** → Mitigation:
  this is private API. Document removal in CHANGELOG. If reported, the
  consumer migration is: read from the DI scope via
  `call_scope.resolve(Principal)` or accept `principal: Principal` as
  a parameter.
- **[Trade-off] One less escape hatch for "I need to peek at the
  current Principal outside dispatch"** → Accepted: this is exactly
  the leak the consolidation is meant to close. If the need is real, a
  documented helper that wraps `call_scope.resolve(Principal)` is the
  right answer.

## Migration Plan

1. Confirm via grep that all stage-level reads of
   `_a2kit_request_principal` are limited to the two cited locations
   in `stages.py`.
2. Delete those reads + the defensive re-seed.
3. Delete the contextvar declaration.
4. Update substrate adapters to write into DI scope (likely no-op if
   they already do; the audit suggests both paths are populated today).
5. Run the existing `principal-propagation` tests; both substrates
   should still pass.
6. Add the new "DI override is sufficient" test.
7. Add the "no provider → clear error" negative test.

Rollback: revert the deletions. The contextvar was load-bearing as a
fallback; restoring it restores the dual path. No data-shape changes.

## Open Questions

- Is there any non-stage code outside the auth substrate adapter that
  reads `_a2kit_request_principal`? Grep + audit during implementation.
  If yes, decide per-call-site (most likely: migrate to
  `call_scope.resolve(Principal)`).
- Should we add the `A2K-NO-PRINCIPAL-CONTEXTVAR` lint rule now or
  defer? Lean defer — the spec-drift gate plus the explicit code
  comment is likely enough.
