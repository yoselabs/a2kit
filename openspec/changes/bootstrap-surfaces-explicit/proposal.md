## Why

The 2026-05-26 parallel-agent structural audit (5 axes, cross-confirmed
on 2 of them) named a `HIGH`-severity hidden-coupling smell:

**Surfaces self-register at import time as a side effect.**

Concrete evidence:

- `src/a2kit/packages/mcp/__init__.py:15-16`:
  ```python
  if "mcp" not in SURFACE_REGISTRY:
      SURFACE_REGISTRY.register_surface(McpSurface())
  ```
- `src/a2kit/packages/http/__init__.py:37-38` does the same for
  `ApiSurface`.

The `if name not in SURFACE_REGISTRY` guard is idempotency theatre —
it doesn't prevent registration, it just silences the duplicate-key
error on re-import. The structural problem stands:

1. **Hidden import-order contract.** Any code that reads
   `SURFACE_REGISTRY` (e.g. `_verbs._validate_expose`, the planned
   `A2K-SURFACE-REGISTRY` lint rule, `serve.py:_surface_has_registrations`)
   must ensure `a2kit.packages.mcp` and `a2kit.packages.http` are
   imported first. The contract is invisible at function signatures.
2. **`_validate_expose` silently no-ops at cold start.** `_verbs.py:100`
   has a cold-start guard that skips `expose=` validation when the
   registry is empty — meaning `@app.read(expose=("mcp",))` written in
   a module that runs before any surface import passes validation that
   should have failed.
3. **Module-level mutation makes the structure opaque to type checkers
   and to the layer DAG.** The layer rules can see `mcp/__init__.py`
   imports `dispatch`; they can't see "and mutates global registry on
   the way."
4. **Future surfaces are pushed into the same shape.** A third
   transport (REST, gRPC, anything in the BACKLOG queue) would
   replicate the self-registration pattern by precedent.

The fix is the same shape that `pipeline.py` already uses for dispatch
stages: an **explicit tuple of surfaces composed at app/runtime build
time**, not import-time accretion. Replace side-effect registration
with explicit declaration; have `AppRuntime.build()` (or `serve()`)
populate the registry from that declaration before any dispatch code
runs.

## What Changes

- **Remove** the import-time self-registration from
  `src/a2kit/packages/mcp/__init__.py` and
  `src/a2kit/packages/http/__init__.py`. The package `__init__.py`
  files become pure-function front doors — no module-level mutation
  of any global.
- **New** explicit composition seam: `AppRuntime.build()` (or the
  closest existing analogue — design.md decides) accepts a `surfaces:
  tuple[Surface, ...]` parameter with a sensible default of `(McpSurface(),
  ApiSurface())`. Both built-in surfaces are registered at runtime
  build time, before any dispatch code runs, in a deterministic order.
- **Replace** `SURFACE_REGISTRY` module-level singleton with a
  per-runtime instance owned by `AppRuntime`. Consumers access it via
  `runtime.surfaces` (or, where `app` is in scope, `app.runtime.surfaces`).
  The module-level singleton stays available as a deprecated shim that
  reads from the active runtime for one release, then is removed in a
  follow-up.
- **Move** `_validate_expose` (currently `_verbs.py:100`) so that
  validation happens at `App.build_runtime()` time instead of at
  `@app.read` decoration time. Decoration captures the `expose` tuple
  unchanged; validation runs once, with the full registry in scope, at
  build time. This eliminates the cold-start no-op silently passing
  invalid `expose=` values.
- **New OpenSpec capability** `serve-topology` (modified): adds the
  requirement that `AppRuntime` is the authoritative owner of the
  surface set, and surfaces are composed explicitly, not registered as
  import side effects.
- **Modified capability** `surface-protocol`: surfaces are
  PASSIVE — they implement the `Surface` Protocol but SHALL NOT
  mutate any global registry at import time.
- The 2026-05-26 audit's Finding 1 (LDD ambient ContextVar trap),
  Finding 2 (`_a2kit_request_scope` silent-None), and the
  `dispatch → signature` layer inversion are addressed by other
  changes (`generalise-context-bridges`, `adopt-arch-fitness-functions`)
  — out of scope here.

## Capabilities

### Modified Capabilities
- `surface-protocol` — surfaces are passive; no import-time registry
  mutation.
- `serve-topology` — `AppRuntime` owns the surface composition;
  surfaces are an explicit constructor parameter, not a global.

## Impact

- Affected code: `packages/mcp/__init__.py`, `packages/http/__init__.py`,
  `packages/dispatch/surface.py` (or wherever `SURFACE_REGISTRY` lives),
  `app.py` / `runtime.py` (where `AppRuntime.build()` composes the
  surface set), `_verbs.py:_validate_expose` (move validation site),
  `serve.py` (registry reads now go through runtime).
- Public API impact: `SURFACE_REGISTRY` as a module-level symbol
  becomes a deprecation shim. Third-party surfaces that called
  `SURFACE_REGISTRY.register_surface(...)` at module-import time keep
  working for one release; the shim emits a `DeprecationWarning`
  pointing at the explicit-composition pattern.
- New deprecation entry in `CHANGELOG.md` `[Unreleased]` for the
  registry shim.
- Cross-ref: 2026-05-26 audit (this conversation; can be captured as
  ADR if needed), BACKLOG entries "Registry-driven `expose=`
  validation" and "`A2K-SURFACE-REGISTRY` lint rule + third-surface
  auto-mount BDD" — both become trivial follow-ups once this lands.
- Sibling changes: `adopt-plugin-manifests` (independent, but the
  manifest discovery becomes the natural fill for the
  `surfaces: tuple[Surface, ...]` parameter once it lands;
  this change does NOT depend on manifest landing first).

## Non-goals

- **Not** changing `Surface` Protocol shape. Surfaces still expose
  the same methods.
- **Not** adding any new surface (REST etc.). Sibling change.
- **Not** removing `SURFACE_REGISTRY` as a name in this change — just
  the import-time mutation pattern. The shim deletion is a follow-up.
