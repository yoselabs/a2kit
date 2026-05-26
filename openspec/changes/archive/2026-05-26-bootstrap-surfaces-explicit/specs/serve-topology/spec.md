## ADDED Requirements

### Requirement: `AppRuntime` owns the surface set via explicit composition

`AppRuntime.build()` (or the canonical runtime-construction seam) SHALL accept a `surfaces: tuple[Surface, ...]` parameter with a default of `(McpSurface(), ApiSurface())`. The constructed runtime SHALL carry a per-runtime surface registry (`runtime.surfaces`) populated from this tuple in the order supplied. There SHALL be exactly one canonical owner of the surface set per runtime — the runtime itself — and no other code path SHALL register a surface after build time.

#### Scenario: Default composition mounts both built-in surfaces

- **GIVEN** a default `App` (no `surfaces=` override)
- **WHEN** `app.build_runtime()` runs
- **THEN** `runtime.surfaces.names()` returns `("mcp", "api")` in declaration order

#### Scenario: Third-party surface composes via explicit argument

- **GIVEN** a custom `class MySurface(Surface)` with `name = "my"`
- **WHEN** `AppRuntime.build(surfaces=(McpSurface(), ApiSurface(), MySurface()))` runs
- **THEN** `runtime.surfaces.names()` includes `"my"`
- **AND** no module-import side effect was required to mount it

### Requirement: `expose=` is validated at runtime build time, not at decoration time

The `@app.read` / `@app.write` / `@app.list_` decorators SHALL capture the `expose=` argument unchanged. Validation against the surface registry SHALL run exactly once, at `App.build_runtime()` time, after the surface set is composed. The previous cold-start no-op in `_verbs.py:_validate_expose` (which silently passed `expose=` validation when the registry was empty at decoration time) is removed.

#### Scenario: Unknown `expose=` value fails at build time

- **GIVEN** a tool decorated `@app.read(expose=("typo-surface",))`
- **WHEN** `app.build_runtime()` runs with the default surface set
- **THEN** build fails with a precise error naming `"typo-surface"` and listing the registered surface names `("mcp", "api")`

#### Scenario: Decoration order does not affect validation

- **GIVEN** `@app.read(expose=("mcp",))` declared in a module imported BEFORE `a2kit.packages.mcp`
- **WHEN** `app.build_runtime()` runs
- **THEN** validation succeeds — because the surface set is composed before validation runs, decoration-time ordering is irrelevant

### Requirement: The module-level `SURFACE_REGISTRY` is a deprecation shim

`a2kit.packages.dispatch.SURFACE_REGISTRY` SHALL remain importable for one release as a deprecation shim. Calls to `.register_surface(...)` on the shim SHALL emit `DeprecationWarning` pointing at the explicit-composition pattern. The shim SHALL be removed in a follow-up change tracked in BACKLOG.

#### Scenario: Legacy call still works with a warning

- **GIVEN** an active `AppRuntime` and a third-party `MySurface()`
- **WHEN** code calls `SURFACE_REGISTRY.register_surface(MySurface())`
- **THEN** a `DeprecationWarning` is emitted
- **AND** `MySurface` is registered on the active runtime's `runtime.surfaces`
