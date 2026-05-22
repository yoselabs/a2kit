## Context

a2kit keeps three artifact layers — CODE (`src/a2kit/`), SPECS
(`openspec/specs/<cap>/spec.md`), DOCS (`README.md`, AGENTS.md, ADRs).
Two of the three have a freshness forcing-function:

- CODE is exercised every commit by `make check` (pytest + ruff + ty +
  `a2kit lint static`).
- DOCS↔CODE is gated by `tests/test_readme_symbol_drift.py` — it parses
  `README.md`, extracts backtick / fenced-block symbols, and asserts
  each resolves on the live `a2kit` surface. It runs in `make lint`.

SPECS have nothing. An OpenSpec capability spec is touched only when a
change explicitly deltas that capability (`## ADDED` / `## MODIFIED` /
`## REMOVED` blocks merged at archive time). A capability nobody deltas
for ten versions is never re-read by any tool. An audit of the 36 specs
under `openspec/specs/` found ~18 drifted: they assert symbols that no
longer exist in code — `a2kit.Param`, `Container._snapshot` /
`_restore` / `_override`, `App.singleton`, `@app.on_startup`, lint
rules `A2K-DI-CHAIN` / `A2K-DI-PROVIDER`. A reader who trusts such a
spec is misled; nothing catches it.

The README gate is the proven shape for catching exactly this class of
rot. The constraint is that it is hard-wired to `README.md` and to a
fixed set of canonical types. The spec tree is a different artifact
(many files, one per capability) but the same mechanical check applies:
a backtick-quoted symbol that looks like a Python name should resolve
in `src/a2kit/`.

A second, orthogonal source of spec rot is **tombstones**. AGENTS.md
mandates that a removed public API leaves a loud-crash-with-hint
("tombstone"): name the removed surface, the replacement, the version.
That doctrine specifies a tombstone's *birth* but not its *death*.
Tombstones accumulate — a v0.33 tombstone is still in the tree at v0.40.
Worse, tombstone behavior has been encoded as Requirements inside
*living* capability specs (e.g. "old `TestClient.override` raises a
migration hint" living in the `test-container-peek` spec). A living
spec asserting a removed-surface raise is drift by construction: when
the raise mechanism is itself removed, the living spec still claims it.

## Goals / Non-Goals

**Goals:**

- A mechanical SPEC↔code gate: every checkable symbol cited in every
  `openspec/specs/*/spec.md` resolves in `src/a2kit/`, or is explicitly
  allowlisted.
- The gate is the README gate's sibling — same resolution approach
  (bind against live types), same `make lint` wiring, low false-positive
  rate via one explicit allowlist.
- The gate's failure output is consumable as a worklist: each line names
  a spec file, a symbol, and why it did not resolve, so
  `reconcile-stale-specs` can work straight off it.
- Record the tombstone-lifecycle doctrine in an ADR so the
  spec-as-tombstone-home anti-pattern stops recurring.

**Non-Goals:**

- Not reconciling the ~18 already-drifted specs — that is the separate
  `reconcile-stale-specs` change this gate feeds.
- Not checking prose claims ("SHALL raise with a hint", "the dispatcher
  enters the resource"). The gate is symbol-resolution only; prose
  correctness stays a review concern.
- Not deleting any existing tombstone or restructuring any spec in this
  change. The ADR records the doctrine; acting on it is downstream.
- Not building a generic OpenSpec linter. The gate is one Python test
  scoped to a2kit's `src/` ↔ `openspec/specs/` pair.
- Not extending the gate to AGENTS.md or `docs/` — README has its gate,
  specs get theirs; other docs are out of scope here.

## Decisions

### D1. New capability `spec-drift-gate`, not an extension of `docs-code-parity`

`docs-code-parity` is named, scoped, and worded entirely around
`README.md` — "README symbol-drift CI gate", "README accurately
reflects the v0.33 public surface", "Canonical-type method drift gate
SHALL extend the README symbol-drift check". Its requirements all bind a
fixed list of canonical types parsed out of one file. The spec-drift
gate is a different artifact tree (36+ files, one per capability), a
different extraction surface (spec prose with `### Requirement` /
`#### Scenario` structure, not fenced `python` blocks), and a different
consumer (its output is a reconciliation worklist). Folding it into
`docs-code-parity` would force that capability to mean "all
artifact↔code parity" — a scope creep that makes the capability name a
lie and entangles two independently-evolving gates. A new capability
keeps each gate's spec readable and lets `reconcile-stale-specs` (and
any future spec-tree work) delta `spec-drift-gate` without touching the
README capability. Chosen: new capability `spec-drift-gate`.

### D2. Bind against live types, do not text-match

The gate imports `a2kit` and resolves each extracted symbol the way the
README gate does: `hasattr(a2kit, name)`,
`importlib.import_module("a2kit.<submod>")` then `hasattr`,
`hasattr(a2kit.App, name)` for `App.x` / `app.x`, etc. A rename that
preserves behavior under a new name still fails the gate, because the
old name no longer resolves. Text-matching `src/` would miss this and
also miss dynamic surface (lazy `__getattr__` exports). Binding against
the imported surface is the only check that matches what a consumer
actually sees.

### D3. What counts as a checkable symbol

The gate extracts only backtick-quoted (code-font) spans from spec
files — prose words in plain text are never checked. Within a code-font
span, a token is *checkable* when it matches one of:

- a dotted a2kit path — `a2kit.X`, `a2kit.<submod>.Y`, optionally
  `@`-prefixed (decorator form);
- an attribute access on a canonical type — `App.x`, `app.x`,
  `Router.x`, `@app.x`, `Container.x`;
- an a2kit lint-rule code — the `A2K-[A-Z0-9-]+` shape (e.g.
  `A2K-LAYER`, `A2K-PKG-FRONT-DOOR`). These resolve against the live
  lint-rule registry, not `hasattr`.

A bare lowercase word in backticks (`provide`, `slug`), a quoted string
literal, a file path, a shell command, a type-annotation fragment
(`Lazy[T]`, `dict[str, int]`), and any token under a known non-a2kit
prefix (`pydantic.`, `fastmcp.`, `typing.`, `ctx.`, `self.`) are *not*
checkable — they are illustrative or third-party and are skipped by
construction. This is the same conservative stance the README gate
takes: only a token with enough structure to be unambiguously an a2kit
symbol claim is checked. Erring toward "not checkable" keeps false
positives near zero at the cost of some false negatives (a dead bare
`provide` would slip through) — an acceptable trade for a gate that
must stay green to be trusted.

### D4. One explicit allowlist for illustrative identifiers

Some code-font tokens are structurally a2kit-shaped but legitimately do
not resolve:

- **Example-only names** — `TrackerStore`, `ProjectsRouter`,
  `MyEvent` — placeholder identifiers a spec uses to illustrate a
  pattern. (The README gate already carries this exact set as
  `_EXAMPLE_ONLY_NAMES`; the spec gate reuses the concept.)
- **Tombstone migration targets** — a spec may cite a *removed* name to
  document its migration (`a2kit.AppBuilder` named in a REMOVED
  requirement's **Migration** line). The name correctly does not
  resolve; that is the point.
- **Grandfathered drift** — when this gate is first landed, the ~18
  already-drifted specs would fail it. To land the gate green (so it
  starts protecting against *new* drift immediately), today's known
  drifting symbols are entered in the allowlist with a `# reconcile:`
  comment tagging them for `reconcile-stale-specs` to remove.

The allowlist is a single module-level constant (a `frozenset` of
symbol strings, or a small dict keyed by symbol with a reason string)
co-located with the gate. Every entry carries a comment naming *why* it
is exempt. The allowlist is the one tuning knob; `reconcile-stale-specs`
shrinks it as it fixes specs. An allowlist that only grows is itself a
smell — but that is a review concern, not something the gate enforces.

### D5. Failure output is a reconciliation worklist

On failure the gate emits one line per unresolved symbol:
`openspec/specs/<cap>/spec.md:<line> — <symbol>: <reason>` (mirroring
the README gate's `README.md:<line> — <sym>: <reason>` format). This is
deliberately the worklist `reconcile-stale-specs` consumes: run the
gate, capture the failure list, fix each spec, remove the matching
allowlist entry. The gate and the reconciliation change are designed as
a producer/consumer pair.

### D6. The gate joins `make lint`, mirroring the README gate

`make lint` already ends with
`uv run pytest tests/test_readme_symbol_drift.py --no-cov -q`. The spec
gate is added as the next line:
`uv run pytest tests/test_spec_symbol_drift.py --no-cov -q`. It is part
of `make lint`, therefore part of `make check` (`check: lint test`) and
of CI and the pre-commit hook, with no separate wiring. Keeping it a
distinct `pytest` line (rather than letting the default test run cover
it) matches the README gate's treatment and makes a spec-drift failure
legible in lint output.

### D7. Tombstone-lifecycle doctrine — recorded in a new ADR (0018)

A new ADR, `docs/adr/0018-tombstone-lifecycle.md` (0018 is the next free
number — 0001–0017 exist, 0016 superseded by 0017), records three
decisions. The ADR file is written as a task in `tasks.md`; this design
fixes its content:

1. **Tombstones are permanent but cheap.** A removed public name keeps
   its loud-crash-with-hint indefinitely (a consumer pinned to an old
   version may upgrade years later and must hit the hint, not an opaque
   `AttributeError`). "Permanent" is affordable only if the mechanism is
   data-driven: one registry dict per module mapping removed-name →
   (replacement, version) plus one module-level `__getattr__` that
   raises from it — NOT a hand-written raise-stub per removed method.
   The data-driven form makes "permanent" a row in a dict, not a
   maintained function.
2. **Removed-surface behavior is NOT a living-spec Requirement.** A
   tombstone's "raises with a hint" behavior, if specced at all, is a
   short-lived `ADDED` requirement *in the change that removes the
   surface*, then `REMOVED` from that capability a couple of minors
   later once no consumer is plausibly still mid-migration. It never
   lives as a standing Requirement in a living capability spec — a
   living spec describes the *current* surface, and a tombstone is by
   definition not current surface. (The current
   `test-container-peek` / `app-builder-runtime` specs that carry "old
   `TestClient.override` raises a migration hint" requirements are the
   anti-pattern this rule names; `reconcile-stale-specs` removes them.)
3. **A superseded capability spec is DELETED, not emptied.** Open
   question resolved: when a whole capability is superseded, its
   `openspec/specs/<cap>/spec.md` file is **deleted** from the spec
   tree (the deletion recorded in the superseding change's spec delta as
   `## REMOVED Requirements` covering the capability, with **Reason** /
   **Migration**). It is NOT left as a husk of `REMOVED` requirements.
   Rationale: `openspec/specs/` is the catalog of *what a2kit does
   today*; a husk file is permanent drift bait (the spec gate would
   have to allowlist every dead symbol in it forever) and misleads any
   reader or tool that enumerates the directory. The OpenSpec archive
   (`openspec/changes/archive/`) already preserves the full history of
   the superseded capability, so deletion loses nothing — the record
   lives in the archive, the catalog stays honest.

### D8. The gate is one file, no new dependency

The gate is a single `tests/test_spec_symbol_drift.py` using only
`re`, `pathlib`, `importlib`, `pytest`, and `a2kit` — the exact
toolbox of the README gate. No new dependency, no new config language.
It is the spec-tree sibling of an existing ~300-line test, not a new
subsystem.

## Risks / Trade-offs

- **False negatives on bare identifiers** → A dead bare `provide` in a
  spec (no `app.` qualifier) is not checkable and slips through.
  Mitigation: accepted by design (D3) — the gate trades recall for a
  near-zero false-positive rate so it stays trusted and green. Dotted
  paths, canonical-type accesses, and lint codes — the bulk of the ~18
  drifted symbols — *are* caught.
- **Allowlist becomes a dumping ground** → grandfathering today's drift
  (D4) seeds the allowlist with ~18 entries; if `reconcile-stale-specs`
  stalls, they linger. Mitigation: every entry carries a `# reconcile:`
  comment, and `reconcile-stale-specs` is explicitly sequenced right
  after this change; an ever-growing allowlist is a visible review
  smell.
- **Two parallel gates drift apart** → README gate and spec gate share
  no code, so a fix to one (a new non-a2kit prefix to skip) is not
  inherited by the other. Mitigation: accepted — the artifacts differ
  enough (fenced `python` blocks vs. spec Requirement/Scenario prose)
  that a shared abstraction would be more coupling than it removes; the
  duplication is ~50 lines of skip-list and resolver, deliberately
  copied.
- **Landing the gate green requires grandfathering** → the gate goes in
  *before* the specs are clean (proposal sequencing), so its first
  commit allowlists known drift. Mitigation: this is intentional — a
  gate landed after the cleanup would not have driven the cleanup. The
  worklist is the point.
- **ADR 0018 doctrine vs. existing specs** → the "tombstones are not
  living-spec requirements" rule (D7.2) immediately makes parts of
  `test-container-peek` / `app-builder-runtime` non-conformant.
  Mitigation: that non-conformance is exactly an item on the
  `reconcile-stale-specs` worklist; the ADR records the rule, the
  follow-up change applies it.

## Open Questions

None outstanding. The one open question carried into this change —
whether a superseded capability spec is deleted or emptied — is resolved
in D7.3 (deleted; the archive preserves history).
