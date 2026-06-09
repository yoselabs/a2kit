## MODIFIED Requirements

### Requirement: `AppRuntime` owns the surface set via explicit composition

`a2kit.runtime.build(app)` (or the canonical runtime-construction seam) SHALL accept a `surfaces: tuple[Surface, ...]` parameter with a default of `(McpSurface(), ApiSurface())`. The constructed runtime SHALL carry a per-runtime surface registry (`runtime.surfaces`) populated from this tuple in the order supplied. There SHALL be exactly one canonical owner of the surface set per runtime — the runtime itself — and no other code path SHALL register a surface after build time.

The CLI is now a `Surface` (`CliSurface`, `kind = SurfaceKind.LOCAL`). The top-level CLI SHALL be assembled by `CliSurface.bind(runtime, descriptors)` rather than by a free `build_full_cli` function outside the surface set. Because the CLI is a `LOCAL`-kind surface it is NOT mounted into the network parent ASGI application (it has no `/cli` HTTP path); it is materialized on demand by the CLI entry point (`a2kit.run`) via its surface's `bind`. The default network `surfaces=` tuple therefore stays `(McpSurface(), ApiSurface())` — the `NETWORK` surfaces — while the `LOCAL` CLI surface participates in the same uniform `bind(...)` protocol without changing the mounted-network default.

#### Scenario: Default composition mounts both built-in network surfaces

- **GIVEN** a default `App` (no `surfaces=` override)
- **WHEN** `a2kit.runtime.build(app)` runs
- **THEN** `runtime.surfaces.names()` returns `("mcp", "api")` in declaration order

#### Scenario: Third-party surface composes via explicit argument

- **GIVEN** a custom `class MySurface(Surface)` with `name = "my"`
- **WHEN** `a2kit.runtime.build(app, surfaces=(McpSurface(), ApiSurface(), MySurface()))` runs
- **THEN** `runtime.surfaces.names()` includes `"my"`
- **AND** no module-import side effect was required to mount it

#### Scenario: CLI is assembled via CliSurface.bind

- **GIVEN** a built runtime
- **WHEN** the top-level CLI is produced (the `a2kit.run` entry point)
- **THEN** the command is built by `CliSurface().bind(runtime)`, not by a free `build_full_cli` function outside the surface set
- **AND** because `CliSurface.kind` is `SurfaceKind.LOCAL`, the CLI is not mounted into the network parent ASGI app
