## 1. BDD specs (write tests first)

- [ ] 1.1 `tests/capabilities/serve_topology/test_no_import_time_registration.py` — importing `a2kit.packages.mcp` and `a2kit.packages.http` SHALL NOT mutate any module-level registry. Assert: a fresh interpreter that only imports the front doors finds `SURFACE_REGISTRY` empty.
- [ ] 1.2 `tests/capabilities/serve_topology/test_runtime_composes_surfaces.py` — `AppRuntime.build()` (or equivalent) populates `runtime.surfaces` from its `surfaces=` argument with deterministic order; default is `(McpSurface(), ApiSurface())`.
- [ ] 1.3 `tests/capabilities/serve_topology/test_validate_expose_at_build_time.py` — `@app.read(expose=("mcp",))` written before any surface import passes decoration unchanged; validation fires when `app.build_runtime()` is called; an unknown `expose=("does-not-exist",)` fails at build time with a precise error.
- [ ] 1.4 `tests/capabilities/serve_topology/test_third_party_surface.py` — passing a custom `MySurface()` via `surfaces=(McpSurface(), ApiSurface(), MySurface())` mounts it without any module-import side effect.
- [ ] 1.5 `tests/capabilities/surface_protocol/test_surfaces_are_passive.py` — every surface class declared under `packages/<x>/` is constructable without raising AND without mutating any global. Architecture-style test (or pytest-archon rule when `adopt-arch-fitness-functions` lands).

## 2. Strip import-time mutation

- [ ] 2.1 Delete the `if "mcp" not in SURFACE_REGISTRY: SURFACE_REGISTRY.register_surface(McpSurface())` block from `packages/mcp/__init__.py:15-16`.
- [ ] 2.2 Delete the equivalent block from `packages/http/__init__.py:37-38`.
- [ ] 2.3 Verify both `__init__.py` files now contain only imports, `__getattr__` (lazy attribute resolution), and `__all__` — no top-level statements that touch any registry.

## 3. Explicit composition at runtime build

- [ ] 3.1 Add `surfaces: tuple[Surface, ...] = (McpSurface(), ApiSurface())` parameter to `AppRuntime.build()` (or the closest seam — design.md resolves the exact site).
- [ ] 3.2 At build time, populate the runtime-scoped registry by iterating `surfaces` and calling `runtime.surfaces.register(s)`.
- [ ] 3.3 Update `serve.py:_surface_has_registrations` and any other registry reader to read from `runtime.surfaces` instead of the module-level singleton.

## 4. Validate `expose=` at build time

- [ ] 4.1 In `_verbs.py:_validate_expose` (line 100), remove the cold-start no-op guard. Instead, change `@app.read` / `@app.write` / `@app.list_` so they capture `expose` unchanged and defer validation.
- [ ] 4.2 In `App.build_runtime()` (or the equivalent), after surfaces are registered, walk every captured tool spec and validate its `expose=` against `runtime.surfaces` names. Fail with a precise error message naming the bad value and listing the known surface names.

## 5. Deprecation shim

- [ ] 5.1 Keep `SURFACE_REGISTRY` as a module-level symbol but make it a thin proxy that reads/writes the active runtime's registry (use a module-level `ContextVar[AppRuntime | None]` or accept the simpler shape where the shim raises if no runtime has been built — design.md decides).
- [ ] 5.2 `SURFACE_REGISTRY.register_surface(...)` raises `DeprecationWarning` and routes to `runtime.surfaces.register(...)` if a runtime is active; raises a clear `RuntimeError` if not.
- [ ] 5.3 Add a one-line follow-up to BACKLOG: "Delete `SURFACE_REGISTRY` shim after one release." Cross-ref this change.

## 6. Docs

- [ ] 6.1 Update `docs/patterns/` with a new entry (or extend an existing composition pattern doc) covering the explicit-bootstrap rule and why import-time registration is forbidden.
- [ ] 6.2 Update `AGENTS.md` (and `CLAUDE.md` overlay if needed) — replace any "self-register your surface" prose with "pass it to `AppRuntime.build(surfaces=...)`".
- [ ] 6.3 `CHANGELOG.md` `[Unreleased]` entry — flag the deprecation; flag that built-in surfaces continue to be registered by default.

## 7. Verification

- [ ] 7.1 `make test` green.
- [ ] 7.2 A fresh interpreter session that imports only `a2kit.packages.mcp` finds `runtime is None` and `SURFACE_REGISTRY` empty (or a shim that says "no runtime active").
- [ ] 7.3 A consumer calling the legacy `SURFACE_REGISTRY.register_surface(MySurface())` AFTER `App.build_runtime()` gets the deprecation warning AND the surface ends up registered.
- [ ] 7.4 An `@app.read(expose=("typo-surface",))` declared anywhere in the codebase fails at `app.build_runtime()` with a precise error.
