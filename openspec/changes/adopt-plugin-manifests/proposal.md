## Why

a2web shipped a single declarative plugin shape (`PluginManifest[T]` +
`Unavailable` sentinel + `load_surface()` reflection) on 2026-05-26
(ADR-0001 Pattern 2, archived change `unify-plugin-manifests`). It
collapsed six drifted extension-point surfaces (tiers, handlers, LLM
providers, sinks, wobble policies, eval systems) into one shape that
unifies *registration*, *capability-aware configuration delivery*,
and *unavailability handling*.

a2kit has several extension-point surfaces that today each
re-discover the registration + unavailability + capability-check
pattern with slightly different shapes:

- **Surface registry** (`A2K-SURFACE-REGISTRY` — backlog calls for
  a lint rule that demands `SURFACE_REGISTRY.register_surface(...)`
  in every `Surface`-implementing package's lazy load).
- **Connections** (`packages/connections/`) — connection types
  register and may be unavailable when credentials are missing.
- **Auth providers** (`APIKeyAuth` today, `JwtAuth` + `GoogleAuth` in
  the backlog) — registered through `App.auth(...)`, gated by env /
  capability presence.
- **LDD sinks** (today `add_sink(callable)`) — about to grow first-class
  defaults (otel sink, live sink) per the LDD reshape change.
- **Codemode tools** — already pluggable, no shared registration shape.
- **`expose=` validation** — backlog calls for registry-driven
  validation (today hardcoded to `{"mcp", "api"}`).

The cost is named in the backlog: registry-driven `expose=` validation
is blocked on the layer relocation question; the `A2K-SURFACE-REGISTRY`
lint rule needs a uniform "MANIFEST goes here" shape to bind against;
the second-auth-provider work duplicates wiring rather than declaring
a manifest.

a2web's `PluginManifest` is generic enough to lift verbatim. It
already namespaces protocol, factory, settings_prefix, priority. The
`Unavailable(reason)` return discipline (over exceptions) is the
right shape for "not configured at boot is expected" — which a2kit's
auth + connections + surfaces all need.

## What Changes

- New private framework module `src/a2kit/packages/_plugin.py`
  porting a2web's `PluginManifest[T]`, `Unavailable`, `load_surface`,
  and `load_surface_sorted`. Module is `_`-prefixed (private to the
  framework); public re-export from `a2kit.packages` is **not** in
  this change — callers stay in-framework until the first external
  consumer asks.
- New OpenSpec capability `plugin-manifest` documenting the shape +
  the `Unavailable`-before-registry invariant.
- One pilot surface migrates in this change: **auth providers**.
  `APIKeyAuth` gains a `MANIFEST = PluginManifest(...)` constant in a
  new `packages/auth/_providers/api_key.py` file, and `App.auth(...)`
  becomes a thin wrapper over `load_surface(...)`. This proves the
  shape against a real surface without touching every surface at once.
- `surface-protocol` capability gains a forward-looking requirement
  that future `Surface` implementations SHALL register via
  `PluginManifest` — the `A2K-SURFACE-REGISTRY` lint rule from BACKLOG
  becomes a one-line pytest-archon rule once
  `adopt-arch-fitness-functions` lands.
- Test rule: every `MANIFEST`-bearing module SHALL be side-effect-free
  at import time (a2web invariant; module imports happen for every
  plugin at boot).
- Sequencing: remaining surfaces (connections, future auth providers,
  ldd sinks, codemode tools, `expose=` validation) migrate in
  follow-up changes, one per session. This change locks the shape;
  follow-ups port surfaces.

## Capabilities

### New Capabilities
- `plugin-manifest` — `PluginManifest[T]` declarative shape +
  `Unavailable(reason)` sentinel + `load_surface()` reflection.

### Modified Capabilities
- `surface-protocol` — adds the forward-looking "Surface
  implementations register via PluginManifest" requirement, gated
  by `plugin-manifest` landing first.

## Impact

- Affected code: new `packages/_plugin.py` (~185 LOC, near-verbatim
  from a2web), new `packages/auth/_providers/api_key.py` (one
  manifest), `packages/auth/__init__.py` (`App.auth` wires through
  `load_surface`).
- Two new dev-time tests: manifest invariant (side-effect-free import)
  + `Unavailable` drop-before-registry.
- No public API change for existing consumers — `App.auth(APIKeyAuth(...))`
  keeps working; the manifest shape is the framework-internal route.
- Cross-ref: a2web ADR-0001 Pattern 2, a2web archived change
  `openspec/changes/archive/2026-05-26-unify-plugin-manifests/`,
  a2kit BACKLOG entries "Registry-driven `expose=` validation",
  "`A2K-SURFACE-REGISTRY` lint rule", "`add-auth-jwt` follow-up",
  "`add-auth-google-oauth` follow-up".

## Open question

Whether this change should also retire the `App.auth(instance)`
imperative-registration API in favour of "discover manifests under
`a2kit.packages.auth._providers/`". a2web went discovery-only; a2kit
has a smaller surface and the imperative API is still easier for
consumer tests. Recommendation: keep both until a real reason to
remove `App.auth(...)` appears; flag in design.md if this change
acquires one.
