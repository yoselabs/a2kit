## Why

A spec audit found that roughly half of the 36 capability specs in `openspec/specs/` have drifted from the code. They assert APIs and symbols that no longer exist (`app.singleton`, `TestClient.override`, `_APP_CTX` in a phantom file, `a2kit.Param`, the `A2K-CORE-CLEAN` lint rule), carry dead "raises with a hint" requirements whose delivery mechanism (`App.__getattr__`) was removed, and in one case (router-slug derivation) three artifacts give three mutually contradictory wrong answers. A spec that lies is worse than no spec: it sends a maintainer or an agent to write code against an API that does not exist. This change reconciles every drifted or stale spec to current code reality so the spec set is once again a trustworthy contract.

## What Changes

- **Repair the 8 DRIFTED specs** — targeted edits to the specific requirements and scenarios whose example symbols, helper names, or function signatures no longer match the code. The capability still exists; only the prose is wrong.
- **Rewrite or gut the 9 STALE specs** — these assert capabilities that were removed, retired, or never shipped. Where a successor capability exists, the requirement is rewritten to describe it; where the capability is genuinely gone, the requirement is REMOVED with a `Reason` + `Migration`.
- **Resolve the router-slug three-way contradiction.** `core-purity` asserts a verbatim-classname fallback, `router-conventions` asserts a `Router`-suffix-strip-and-lowercase derivation, and the code (`src/a2kit/routers.py`) requires an explicit `slug: str` class attribute and raises if it is absent. The code is canonical: both specs are aligned to "explicit `slug` required, no derivation."
- **BREAKING (spec contract, not code):** dead "removed method SHALL raise with a hint" requirements are deleted. `app.singleton`, `App.singletons`, `App.has_singleton` now raise plain `AttributeError` (the `__getattr__` interceptor that produced the hinted `TypeError` was removed in the app-runtime internalization). The spec stops promising a hint the framework no longer delivers.
- **Fix one genuine live bug** as part of this change: `src/a2kit/_lifecycle_helpers.py` (~lines 37-45) emits error messages telling users to call `app.singleton(...)`, a method that does not exist. The messages must name `app.provide`. This is the only code edit in scope; it is captured as an implementation task and is done at apply time.
- This change **depends on `add-spec-drift-gate`** (a separate change). That gate enumerates the dead-symbol worklist this reconciliation clears, and it owns the decision on the mechanism for deleting a spec entirely (OpenSpec may only support emptying a spec via REMOVED requirements, not removing the directory).

Out of scope: authoring brand-new specs for code that currently has none (`signature.py`, `metadata.py` / `A2KitMeta`, `schema.py`, `exceptions.py`, individual lint-rule families). This change reconciles existing specs; the coverage gaps are listed under Impact as follow-up.

## Capabilities

### New Capabilities

<!-- none — this change reconciles existing capabilities; it introduces none -->

### Modified Capabilities

STALE (heavy rewrite; dead requirements REMOVED):

- `app-singletons`: capability is now the `provide` API. Two dead "removed `singleton`/`has_singleton`/`singletons` SHALL raise with a hint" requirements are deleted (the `__getattr__` delivery mechanism is gone). The "`App.teardown_failures`" requirement is deleted (`teardown_failures` does not exist on `App`; teardown isolation is the `di-scope-cleanup-stack` contract).
- `core-purity`: the `A2K-CORE-CLEAN` rule it polices was retired in v0.34; the verbatim-classname router-slug fallback it asserts is wrong. Requirements that depend on the retired rule and the wrong fallback are REMOVED; the still-true requirements are kept.
- `di-container-package`: the `Container._snapshot` / `_restore` test seam it requires does not exist; `register` is listed as a current method but is retired. Those requirements are corrected.
- `in-process-test-client`: the "TestClient.override swaps dependencies" requirement is fully dead (`override` removed v0.40); it also references nonexistent `@app.on_startup`/`@app.on_shutdown` and removed `App(health_tool=True)` / `app.singleton(...)`. Dead requirement REMOVED; stale scenarios repaired.
- `module-layout-discipline`: self-contradicts ("no underscore-prefixed modules with public symbols" vs. requiring `_verbs.py` / `_verb_validators.py` to exist); asserts `_APP_CTX` in a `packages/cli/app_ctx.py` that does not exist; names exemplar files `decorator.py` / `enrichers.py` that do not exist. Contradiction resolved; phantom-file claims corrected.
- `request-scoped-di`: asserts the `_override`/`_snapshot`/`_restore` seam "remains" (false); references lint rules `A2K-DI-CHAIN` / `A2K-DI-PROVIDER` that do not exist; scenarios use `app.singleton(...)`. Corrected to the live `provide` surface.
- `router-conventions`: the slug-derivation requirement is wrong (code requires an explicit `slug`); the enrichers requirement references a removed `a2kit.packages.enrichers` module. Slug requirement rewritten to match code; enricher requirement reconciled.
- `thin-core-surface`: a v1.0-era museum spec asserting `uncalled_for` / `Depends`, `dependency_overrides`, `App.use_factory`, `packages/enrichers/` + `packages/middlewares/`, `--format=toon`, and core files `runner.py` / `cli.py` — none of which exist. Superseded requirements REMOVED; the few still-true ones kept.
- `tool-description-contract`: asserts an `a2kit.Param` class for per-parameter descriptions; no `Param` class exists anywhere in `src/a2kit/`. The `Param` requirement is REMOVED (capability unimplemented).

DRIFTED (targeted repair):

- `app-lifecycle`: stale `ToolError` / `ShutdownError` framing in one scenario; minor overlap with `di-scope-cleanup-stack`.
- `core-composition`: a requirement about a removed purity lint rule; coordinated with `core-purity`.
- `docs-code-parity`: requirement text embeds stale example symbols (`app.singleton`, `Router.providers`, `App.singleton(..., teardown=...)`).
- `health-probe`: a scenario calls `run_checks(app)` but `run_checks` takes a `Resolver`, not an `App`; references a removed `lifespan_cm()`; uses `app.singleton`.
- `mcp-context-passthrough`: scenarios use removed `on_startup` and `app.singleton`.
- `mcp-tool-annotations`: references `@a2kit.tool` (removed v0.33).
- `operational-contracts`: scenarios use `@on_startup` / `@on_shutdown`, `health_tool=True`, `app.singleton`.
- `type-driven-format-routing`: names underscore-private `_infer_format_hint` / `_is_dump_scalar`; the code exposes a public `infer_format_hint`.

## Impact

- **Specs**: 17 capability spec files reconciled (`openspec/specs/<name>/spec.md` for each capability above). No live spec is edited directly; the change ships delta files under `specs/`.
- **Code**: exactly one edit — `src/a2kit/_lifecycle_helpers.py` error messages renamed `app.singleton` → `app.provide` (apply-time task). No other `src/`, `tests/`, or `docs/` changes.
- **Dependency**: blocked on `add-spec-drift-gate` for the dead-symbol worklist and for the spec-deletion mechanism decision.
- **Not touched**: `tool-descriptors` is owned by the separate `remove-dead-surface` change and is deliberately excluded.
- **Follow-up (out of scope)**: code with no spec at all — `signature.py`, `metadata.py` (`A2KitMeta`), `schema.py`, `exceptions.py`, and the per-family lint rules — should get new specs in a later change. This reconciliation only repairs existing specs.
