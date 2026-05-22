---
id: "0015"
status: accepted
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: []
superseded_by: null
tags: [architecture, packaging, lint, imports]
deciders: [Denis Tomilin]
---

# ADR 0015: Internal layer DAG — the import graph is tiered and lint-enforced

## Status

Accepted, 2026-05-22.

## Summary

In the context of a2kit's internal import graph, facing function-local and `TYPE_CHECKING` imports being used to paper over package import cycles — and ADR 0004 tiering only the *public surface*, not the *dependency graph* — we decided for an explicit layer manifest enforced by two lint rules (`A2K-LAYER` and `A2K-PKG-FRONT-DOOR`), and against relying on convention, to achieve a dependency graph that fails the build when a regression is introduced (a new cycle, an upward import, a past-the-front-door import — including type-only ones), accepting a manifest that must be edited when a package changes layer and a small allowlist for the public re-export facades.

## The problem

ADR 0004 tiers a2kit's *public Python surface* by audience size. It says nothing about the *internal dependency graph* — which package may import which. That was left to convention, and convention does not hold.

The `decouple-import-cycles` change found four suspected import cycles (three real). Every one was hidden the same way: a function-local import, or a `TYPE_CHECKING`-guarded import, that kept the module-scope graph looking acyclic while the design cycle was still there. `mcp/_wrappers.py` carried 21 `: Any` annotations purely because importing the real `App` / `Router` types would have closed an `mcp ↔ cli` cycle. Nothing failed the build; the rot was invisible until someone read for it.

The same is true of *layering*. `cli`, `mcp`, `codemode` sit above the kernel packages, which sit above core — but that is a fact you learn by reading, not a gate. And ADR 0004 declares `a2kit.packages.X.__init__` the front door, yet `app.py` reached straight into `packages.di.container`, `packages.di.scope`, `packages.di.resolver`, `packages.formatter.inference` — past every front door, with nothing to stop it.

Three structural facts were unenforced: there was no layer DAG, `core` was an unmodeled participant in that DAG (it both imports kernel packages and is imported back by them), and package front doors were decorative.

## What we considered (and why this one)

### Option 1: Keep it convention; rely on code review

Why it lost: convention already failed — three real cycles shipped. Review does not reliably catch a function-local import three levels deep, and a `TYPE_CHECKING` cycle is invisible to the type checker too. A regression gate has to be mechanical.

### Option 2: A third-party import-graph linter (`import-linter`, `tach`)

Why it lost: a2kit already owns a static-lint harness (`a2kit lint static`, the `A2K-*` rule family) wired into `make lint` and the pre-commit hook. A second tool means a second config language, a second failure surface, and a second thing to keep current. The layer check is ~150 lines on top of the existing harness; adopting a dependency to save that is the wrong trade for one repo.

### Option 3: Layer manifest + two lint rules in the existing harness (chosen)

A flat `dict[str, int]` manifest in `packages/lint/layers.py` assigns every unit a layer. Two rules enforce it:

- **`A2K-LAYER`** — a unit may import only strictly-lower layers (plus its own); a same-layer import must not close a cycle. It resolves every import to its manifest unit, governs core↔package edges in both directions, and inspects `TYPE_CHECKING`-guarded imports (a type-only cycle still constrains every future refactor, so it is still a cycle).
- **`A2K-PKG-FRONT-DOOR`** — a cross-package import must target `a2kit.packages.X`, never a deep submodule.

Why it wins: it reuses the harness the team already runs, it makes the regression loud at `make lint` time, and the manifest is a single declarative artifact a reader can load to see the whole intended graph. It is the internal-graph sibling of ADR 0004's audience-tiered public surface.

## The decision

### The layer manifest

Units are the directories under `src/a2kit/packages/` plus one `core` pseudo-unit (the top-level `a2kit.*` modules). The manifest (`a2kit.packages.lint.layers.LAYER_MANIFEST`):

- **L0 — kernel:** `di`, `formatter`, `ldd`, `select`, `lint`, `context`, `health`. Foundational; depend only on each other (acyclically) and on the foundational core modules below.
- **L1 — core:** the `a2kit.*` composition modules (`app`, `tool`, `routers`, `signature`, `metadata`, ...). Imports kernel packages; imported by everything above.
- **L2 —** `connections`, `dispatch`. Above core, below the transports.
- **L3 — transports:** `cli`, `mcp`, `codemode`, `otel`.
- **L4 —** `testing`, the test surface, on top of everything.

A unit may import only strictly-lower layers, plus its own. A same-layer import is allowed only when it closes no cycle.

### Core is a layer, not an exempt zone

The worst cycle `decouple-import-cycles` found — `app.py ↔ packages/health` — spanned the core boundary. A layer model covering only `packages/*` is blind to it. So `core` is a unit in the manifest (L1), and `A2K-LAYER` governs core↔package edges in both directions.

`core` is one unit; intra-core module ordering is out of scope (a unit is one node). Two genuinely foundational core modules — `a2kit.exceptions` and `a2kit._context_protocol` — are leaf type/exception definitions that import nothing; they are treated as layer-exempt import *targets* (the bedrock below every layer), so a kernel package's `from a2kit.exceptions import ...` does not read as an upward `core` edge.

### Facades are exempt

The public re-export facades — the package root `__init__.py` files and `a2kit/testing.py` (the Tier-2 test-surface shim) — exist to surface deeper layers as a flat public API. They import "upward" and reach past front doors by design. `__init__.py` files are skipped; `a2kit/testing.py` is named in a documented exempt list. `A2K-PKG-FRONT-DOOR` also ships an allowlist constant (empty by default; every entry needs a comment) for any future deliberate deep import.

### Front doors are the only door

`a2kit.packages.X.__init__` is the front door (ADR 0004); `A2K-PKG-FRONT-DOOR` makes it the *only* door. Cross-package imports target `a2kit.packages.X`. A module reaching a sibling inside its own package is internal wiring and is fine.

## Consequences

### Positive

- A new cycle (runtime or type-only), a new upward import, or a new past-the-front-door import fails `make lint`. The regression is mechanical, not review-dependent.
- The manifest is a single loadable artifact: a reader sees the entire intended dependency graph in one ~20-line dict.
- The rule pair caught — and the `decouple-import-cycles` / `extract-dispatch-pipeline` changes then fixed — every deep import in core (`app.py`, `signature.py`, `tool.py`) onto the package front doors.

### Negative

- Moving a package between layers is a manifest edit. That is intentional friction — a layer change is a real architectural decision — but it is friction.
- The `core` pseudo-unit is coarse: it cannot catch a cycle *between two core modules*. That is accepted scope (intra-core ordering is out of scope); module-level acyclicity within core is left to `A2K-PKG-INIT-IMPORT` and review.
- The foundational-module and facade exemptions are a small special-case surface. They are documented in `layers.py` and here, but they are exceptions a future reader must know about.

## References

- `src/a2kit/packages/lint/layers.py` — the manifest, the foundational-module set, the facade exempt list.
- `src/a2kit/packages/lint/rules/importing.py` — `A2K-LAYER` and `A2K-PKG-FRONT-DOOR`.
- ADR 0004 — the audience-tiered *public surface*; this ADR is its internal-graph sibling.
- `ANTIPATTERNS.md` #27 — function-local / `TYPE_CHECKING` imports used to dodge a cycle.
- The `decouple-import-cycles` and `enforce-package-layering` OpenSpec changes.
