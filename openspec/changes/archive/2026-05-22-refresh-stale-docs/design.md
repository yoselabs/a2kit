## Context

a2kit is at v0.39.3, pre-1.0, solo-maintained, with a deliberately
fast release cadence — ~7 minor releases removed or reshaped public
surface in the recent past (`@a2kit.tool` gone v0.33, `health_tool=`
gone v0.35, TOON dropped, `aclose`/`close` auto-detection gone v0.36,
LDD primitives moved to `a2kit.ldd` free functions, `AppBuilder`
collapsed into `App`).

The only automated drift guard is `tests/test_readme_symbol_drift.py`.
It is narrow by design: it parses `README.md`, extracts symbol
references that match a fixed set of patterns (`a2kit.X`, `@a2kit.X`,
`App.method`, `Router.attr`, `@app.X`, `a2kit.<submodule>.Y`), and
asserts each resolves on the live module surface. It explicitly
tolerates false negatives for "symbol claimed in prose without
backticks" and it only reads `README.md`.

That leaves three classes of doc text unchecked:

1. **Non-README docs** — `ANTIPATTERNS.md` and
   `OPERATIONAL_CONTRACTS.md` are never parsed by any gate.
2. **Prose and example code that names removed APIs without matching
   a tracked pattern** — e.g. a markdown table cell, or `app.singleton`
   inside a fenced block that the gate would catch *in README* but
   never sees in `OPERATIONAL_CONTRACTS.md`.
3. **ADR frontmatter** — `status:` is hand-maintained; nothing
   verifies a `proposed` ADR has not, in fact, shipped.

An audit walked these three surfaces against the live code and
CHANGELOG. This change applies the audit's findings. It is a
mechanical doc-correctness pass, not a redesign.

## Goals / Non-Goals

**Goals:**

- Every example and symbol reference in `README.md`,
  `ANTIPATTERNS.md`, and `OPERATIONAL_CONTRACTS.md` names an API that
  exists on the v0.39 live surface.
- ADR 0013 and 0014 `status` reflects reality (`accepted` — both
  shipped); `INDEX.md` is regenerated, not hand-edited.
- The fixes preserve each doc's intent. Where an antipattern's
  *lesson* is still valid but its *cited API* changed (e.g. #14: "do
  not fold structured findings into log strings"), the lesson is kept
  and only the example is corrected. Where the lesson itself is dead
  (#9: the TOON encoder no longer exists in any form), the entry is
  rewritten to the current model rather than deleted, so the
  reasoning is preserved.

**Non-Goals:**

- No new automated gate. Extending the drift test to non-README docs
  or ADR frontmatter is a real follow-up but a separate change with
  its own design cost; it is out of scope here. This change records
  the *standard* in the `docs-code-parity` spec without committing to
  a specific new gate.
- No re-flagging the `AppBuilder`→`App` collapse — README and
  AGENTS.md were already refreshed for it.
- No ADR *content* rewrites. Only the `status` field of 0013/0014
  moves. Auth ADRs 0010-0012 stay `proposed` (no auth code exists).
- No changes to `src/`, no public-surface change, no behavior change.

## Decisions

### D1. Rewrite dead antipattern #9, do not delete it

Antipattern #9 ("Don't ship a TOON encoder; use the vetted dep") is
fully dead: TOON was dropped, `formatter/toon.py` does not exist, and
`format_hint="toon"` is gone. The numbering is already pre-v1.0 and
carries a "Retired entries" block for removed entries, so deletion is
structurally available.

Decision: **rewrite** #9 rather than retire it. The underlying lesson
— "do not hand-roll a wire encoder; route every result through one
seam" — is still true and still load-bearing; the current seam is
`render(value, consumer)` in `a2kit.packages.formatter` with TSV /
page-tsv as the compressed wire shapes (per ADR 0014). Rewriting keeps
the antipattern teaching something true. Retiring it would lose the
"one seam, one upstream" reasoning that still applies. Alternative
considered (move #9 to the "Retired entries" block): rejected — the
concern is not retired, only its target format is.

### D2. Correct antipattern #14 in place — keep the lesson, fix the API

Antipattern #14 ("Don't fold structured findings into log strings")
is correct in spirit. Two surface facts in it are stale: it names a
`report=ReportT` verb kwarg (current kwarg is `reports=`, plural,
confirmed in `examples/tracker/routers.py` and the lint rule
`packages/lint/rules/ldd.py`) and it shows `ctx.event(...)` /
`ctx.report(...)` method form (LDD primitives are now `a2kit.ldd`
free functions — `a2kit.ldd.event`, `a2kit.ldd.report`). Fix both
references; the prose and the lesson stand.

### D3. Rewrite OPERATIONAL_CONTRACTS Q3/Q7/Q8 examples to the live App API

`App` exposes `provide`, `health_check`, `add_router` (verified
against `src/a2kit/app.py`). It has no `on_startup`, `on_shutdown`,
`singleton`, or `_singletons`. The removed-API references are:

- Q3 internals list: `app._singletons`, `@app.on_startup` /
  `@app.on_shutdown`, and `app.singleton` in the tool-author note.
- Q7: `_meta.health` "registered via `App(name, health_tool=True)`" —
  `health_tool=` was removed v0.35 and now actively raises `TypeError`
  with a migration message (`src/a2kit/app.py` lines 144-146). The
  live registration path is the `@app.health_check` decorator.
- Q8: `@on_startup` / `@on_shutdown` named as the pre-dispatch
  contexts where LDD primitives raise `AmbientContextMissing`, and an
  `app.singleton(Pool, make_pool)` example.

Decision: rewrite each example and internals reference to the current
API — DI singletons are `app.provide(T, factory)` (app-scope is the
default), the imperative startup/shutdown bookends are expressed as
DI-managed resources with `__aenter__`/`__aexit__` (the v0.36 model
already documented in Q-DI of the same file), and health registration
is `@app.health_check`. The Q8 "pre-dispatch context" point survives
— it just names "module-level code or a warm-up script" instead of
the removed lifecycle decorators. This keeps Q3/Q7/Q8 internally
consistent with Q-DI and Q-HealthChecks, which are already current.

### D4. Flip ADR 0013/0014 to `accepted`; regenerate INDEX via make

`docs/adr/INDEX.md` is auto-generated by `make adr-index`. Decision:
edit only the `status:` line in the two ADR frontmatter blocks, then
run `make adr-index` to regenerate `INDEX.md` — never hand-edit
`INDEX.md`. `make adr-check` verifies the index is in sync. Evidence
that 0013/0014 shipped: `packages/codemode/` exists with `marshal.py`
/ `runtime.py` / `stubs.py`; `packages/formatter/render.py` exists;
CHANGELOG and `OPERATIONAL_CONTRACTS.md` Q-CodeMode / Q-FormatRouting
describe both as landed behavior. Auth ADRs 0010-0012 have no
in-repo auth code and stay `proposed` — verified against `BACKLOG.md`,
which records no auth implementation work as done.

### D5. Spec delta is a single honest MODIFIED requirement

This is a docs change; it has no framework-behavior delta. But it does
strengthen one expectation: the `docs-code-parity` capability so far
only spoke of README *exported symbols*. This change holds the
non-README docs and ADR bodies to the same "no removed APIs in
examples" standard. That is a genuine, narrow expansion of the
capability's intent, so it earns one MODIFIED requirement — recording
the standard, not inventing a new automated gate. No `ADDED` /
`REMOVED` requirements; nothing is being newly built or torn out.

## Risks / Trade-offs

- **The drift recurs.** [Risk] → This change fixes the docs but adds
  no gate for non-README docs, so the same drift can re-accumulate.
  Mitigation: the `docs-code-parity` MODIFIED requirement records the
  standard explicitly, making a future "extend the drift gate to all
  docs" change a clear, scoped follow-up rather than a rediscovery.
- **Rewrite vs. delete judgement for #9.** [Risk] → Rewriting a dead
  antipattern risks the rewrite itself drifting. Mitigation: the
  rewrite targets `render(value, consumer)` / TSV, which is anchored
  by ADR 0014 and exercised by the formatter test suite — a stable
  target, not a moving one.
- **ADR status is still hand-maintained.** [Risk] → Flipping
  0013/0014 fixes today's snapshot but the next shipped-but-`proposed`
  ADR will need another manual pass. Mitigation: accepted as
  pre-1.0 cost; an automated ADR-status check is a possible future
  item, noted but not in scope.
- **Low blast radius.** No code changes, so no test regression risk
  beyond `test_readme_symbol_drift` (which only gets *less* to flag
  after the README row deletion) and `make markdown-lint` /
  `make adr-check` on the edited files.
