---
id: "0032"
status: proposed
date: 2026-06-28
last_reviewed: 2026-06-28
supersedes: []
superseded_by: null
tags: [architecture, surface, packaging, dependency, cli, http, strategy]
deciders: [Denis Tomilin]
---

# ADR 0032: Re-found a2kit as à-la-carte FastMCP helpers (retire the App framework)

## Status

Proposed, 2026-06-28. Captures a 2026-06-28 substrate-strategy brainstorm
backed by an external research pass (a2kit vs FastMCP vs SkyBridge; FastMCP
contribution-culture PR audit). Awaits human confirmation (Constitution
Phase A).

**On acceptance this ADR supersedes ADR 0028 (unified-surface architecture)
and ADR 0019 (app-runtime split)** — both presuppose `a2kit.App` as the one
public type, which this decision removes. It also **deprioritizes ADR 0031
(MCP Apps support)** to a thin `ui://` surface at most (rich UI is a
JS-bundler problem; see The decision). Supersession of 0028/0019 is left
unmarked in frontmatter until acceptance to avoid premature status drift.

## Summary

In the context of a2kit's identity as an opinionated Python MCP framework, facing FastMCP 3.x shipping native code mode, tool-failure responses, multi-transport, and CLI generation — which collapsed a2kit's per-feature moats and turned every FastMCP release into a delete-and-adopt maintenance treadmill — we decided for re-founding a2kit as a set of à-la-carte, independently-extractable helpers over FastMCP (no shared core, no `App`) and against keeping it as a competing framework, to achieve a treadmill bounded to FastMCP's stable public API plus a one-helper→one-upstream-PR contribution pipeline, accepting the deletion of `a2kit.App` and a from-near-scratch rewrite of the public surface that supersedes ADRs 0028 and 0019.

## The problem

a2kit is built **on** FastMCP (it lazily re-exports `fastmcp.Context` and
drives `fastmcp.Client`). Its headline deltas were multi-transport
(one verb → MCP + HTTP + CLI), code mode, and a typed wire surface. As of
FastMCP 3.0 (2026-02) and 3.1, three of those are shipped natively:

- **Code mode** — `transforms=[CodeMode()]`, sandboxed on Pydantic's Monty.
- **Tool-failure responses** — native, which is the immediate trigger for
  this ADR: a2kit now carries a redundant wrapper for it.
- **Transports** — stdio / Streamable-HTTP / WebSocket native.
- **CLI generation** — `fastmcp generate-cli` (a reconnecting client).

The bottleneck is not any one feature — it is the **maintenance treadmill,
and it is proportional to a2kit's surface *overlap* with FastMCP.** Every
FastMCP release that lands a feature a2kit also built forces a
delete-and-adopt cycle. The diagnosis from the strategy review: the breaks
are not self-inflicted internal coupling to FastMCP internals; they are
(a) normal downstream exposure to FastMCP public-contract changes, plus
(b) FastMCP shipping near-equivalents of things a2kit built, which we then
delete. Both are minimized only by **shrinking overlap.**

`a2kit.App` (ADR 0019, "the one public type") is the structural anchor of
that overlap. Because every surface composes through `App`, (1) a FastMCP
change cascades through the whole framework, and (2) no individual a2kit
capability can ever be lifted out and proposed upstream — `App` chains it
down. The framework shape is what makes both the treadmill and the
"can't contribute pieces upstream" problem inevitable.

## What we considered (and why this one)

- **Status quo — keep a2kit as a framework built on `App`.** The treadmill
  is unbounded: overlap grows every FastMCP release, and we keep losing a
  feature race against a ~25k-star project on its own turf. Rejected: the
  cost we are trying to remove is precisely the framework posture.
- **Fork FastMCP.** Maximizes the treadmill — we would own FastMCP's entire
  surface *and* owe ourselves a perpetual upstream merge. Strictly worse on
  the exact axis we are optimizing. Rejected.
- **Cosmetic rename to "fastmcp-extra" / companion branding.** Does not
  change coupling, so does not touch the treadmill; and using the FastMCP
  name implies endorsement, inviting the friction FastMCP's CONTRIBUTING
  explicitly warns about ("ship third-party integrations as standalone
  packages"). Rejected as a non-fix.
- **Re-found as à-la-carte helpers, no shared core (chosen).** Couples a2kit
  only to FastMCP's *stable public API*, so most FastMCP releases no longer
  force deletes; and it makes each helper an independently donatable unit,
  turning a2kit into a contribution pipeline rather than a competitor.

## The decision

Delete `a2kit.App` and the framework spine. Delete the surfaces FastMCP now
owns: code mode, tool-failure-response wrapping, transport plumbing, and
CLI-generation-as-framework. Re-found a2kit as a set of **independently
importable helpers**, each depending **only on `fastmcp` + `pydantic` +
stdlib** — never on a shared a2kit core, `App`, DI container, or config.

```
  OLD (framework)                NEW (à-la-carte, extractable)
  ───────────────                ─────────────────────────────
  a2kit.App  ← god object        (no App — deleted)
    ├ DI container               a2kit.tsv     → typed TSV result type +    ┐
    ├ config                     │               serializer (the one piece  │ each
    ├ transports  (delete)       │               that genuinely needs a     │ depends
    ├ code-mode   (delete)       │               decorator — durable core)  │ ONLY on
    ├ tool-failed (delete)       a2kit.errors  → unified error envelope      │ fastmcp +
    └ everything coupled         a2kit.rest    → verb→REST projection (opt)  │ pydantic
                                 a2kit.cli     → verb→CLI adapter (opt)      │ + stdlib
  consumer:                      a2kit.lint    → static analyzer / CLI       │
  my_server → a2kit.App                          (zero runtime coupling)    ┘

  consumer (new):  my_server → fastmcp   (the base)
                             + a2kit.tsv, a2kit.errors  (sprinkled, optional)
```

**Governing constraint (the rule this ADR exists to enforce): no shared
a2kit core.** No `App`, DI scope, config object, or internal substrate that
helpers depend on. The **extractability invariant**: any helper must be
liftable into FastMCP as *copy one file + open one issue*. A future change
that introduces cross-helper coupling, or re-introduces an `App`-like spine,
is rejected by citing this ADR — the coupling is what the treadmill was made
of.

Consumer projects depend on **FastMCP directly**; a2kit is an optional
add-on dependency for the few durable extras. Delivery is **migration-first**
(see the OpenSpec change, to be authored): port one representative server to
plain FastMCP, write missing helpers inline, let real usage fix each helper's
FastMCP-native signature, then extract the proven helpers into the new a2kit
and delete the framework in the same pass. Each extracted helper is recorded
with the FastMCP gap it fills — that list is the upstream-contribution
backlog.

MCP Apps (ADR 0031) is deprioritized: rich multi-file UI is bundled by a JS
toolchain (Vite/`vite-plugin-singlefile`) or hosted as an external SPA, and
FastMCP already ships prefab UI providers. a2kit caps at a thin `ui://`
surface for templated widgets, if anything at all.

## Consequences

### Positive

- **The treadmill collapses.** a2kit couples only to FastMCP's stable public
  API; releases that add framework features no longer force a2kit deletes,
  because a2kit is no longer in the framework-feature race.
- **Each helper becomes a donatable unit.** "Migrate a piece to FastMCP"
  becomes copy-one-file + open-one-issue, converting a2kit into a
  contribution pipeline (one helper → one scoped upstream proposal) — which
  is the project's new strategic purpose.
- **Smaller blast radius per change.** Independent helpers fail
  independently; a bug in `a2kit.rest` cannot break `a2kit.tsv`.
- **`a2kit.lint` is the most durable asset** — a static analyzer with zero
  runtime coupling, in a governance niche FastMCP's "unopinionated, ship-a-
  package" philosophy will not absorb.

### Negative

- **`a2kit.App` is deleted — this is a re-founding, not a refactor.** It is
  the one public type; removing it supersedes ADR 0028 and ADR 0019, breaks
  the `tests/surface/` snapshots (expected_tier1, expected_lazy_attrs), and
  obsoletes the tiered-surface framing of ADR 0004. Every consumer server
  must be rewritten onto plain FastMCP. Scope this as a rewrite of the public
  surface, not a cleanup.
- **a2kit loses the "my framework" identity.** It is now explicitly an
  optional helper bag over someone else's framework — accepted deliberately;
  the recognition goal moves to FastMCP contributorship, not to a2kit's
  standalone footprint.
- **Some composition convenience is lost.** "One decorator does CLI + REST +
  MCP from one definition" is intentionally given up; consumers wire FastMCP
  plus discrete helpers. Accepted: the unified decorator was the
  framework-shaped ambition that caused the overlap.
- **Helper duplication risk.** Forbidding a shared core means small repeated
  scaffolding across helpers. Accepted as the price of extractability — a
  shared core is exactly what blocks upstreaming.
- **The typed-TSV core remains genuinely a2kit's** (it needs a decorator/
  result-type and is the least FastMCP-overlapping piece); it is unlikely to
  be upstreamed and so anchors a2kit's continued, if minimal, existence.

## References

- FastMCP 3.0 / 3.1 release notes and code-mode post (native code mode on
  Monty; transports; `generate-cli`): <https://gofastmcp.com/changelog>,
  <https://jlowin.dev/blog/fastmcp-3-1-code-mode>.
- FastMCP CONTRIBUTING (enhancements need an assigned issue first;
  third-party integrations ship as standalone packages):
  <https://github.com/PrefectHQ/fastmcp/blob/main/CONTRIBUTING.md>.
- 2026-06-28 substrate-strategy research pass (private; a2kit vs FastMCP vs
  SkyBridge, code-execution paradigm, FastMCP PR-acceptance audit).
- Supersedes on acceptance: ADR 0028 (unified-surface), ADR 0019
  (app-runtime split); deprioritizes ADR 0031 (MCP Apps).
- Delivery: OpenSpec change `refound-a2kit-as-fastmcp-helpers` (to be
  authored) — migration-first sequence, extractability invariant as the
  fitness function.
