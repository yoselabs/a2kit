# surface-protocol Specification

## Purpose

The framework's extension point for substrate adapters. The `Surface`
Protocol is the contract every substrate (MCP, HTTP, future A2A / gRPC
/ GraphQL) satisfies; the `DecoratorSurface[R]` template carries the
shared registration accumulator; `SURFACE_REGISTRY` is the single
ordered registry of mounted surfaces.

Materialized from `add-surface-protocol-additive` (archived 2026-05-24).
The companion `remove-substrate-literal` change rips out the
`Substrate = Literal["fastapi", "fastmcp"]` discriminator and rewires
the dispatch-layer signature splitter to consume `Surface` ClassVars
directly.
## Requirements
### Requirement: `Surface` Protocol is the contract for substrate adapters

`a2kit.packages.dispatch.surface` SHALL define a `runtime_checkable` `Surface` Protocol with: `name: ClassVar[str]`, `kind: ClassVar[SurfaceKind]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`. The `kind` field SHALL be a `SurfaceKind` enum with exactly two members, `NETWORK` and `LOCAL`, distinguishing transports reachable over the network (MCP, HTTP) from process-local transports (the CLI). Substrate adapters (MCP, HTTP, CLI, future) SHALL satisfy this Protocol: `McpSurface` and `ApiSurface` declare `kind = SurfaceKind.NETWORK`; `CliSurface` declares `kind = SurfaceKind.LOCAL`. The `Substrate = Literal["fastapi", "fastmcp"]` discriminator stays unchanged in this capability; its removal lives in `remove-substrate-literal`.

#### Scenario: McpSurface, ApiSurface, and CliSurface satisfy Surface

- **WHEN** `isinstance(McpSurface(), Surface)`, `isinstance(ApiSurface(), Surface)`, and `isinstance(CliSurface(), Surface)` are evaluated
- **THEN** all three return `True`

#### Scenario: kind distinguishes network from local surfaces

- **WHEN** the `kind` ClassVar of each bundled surface is inspected
- **THEN** `McpSurface.kind` and `ApiSurface.kind` are `SurfaceKind.NETWORK`
- **AND** `CliSurface.kind` is `SurfaceKind.LOCAL`
- **AND** `SurfaceKind` has exactly the two members `NETWORK` and `LOCAL`

### Requirement: `SurfaceRegistry` is the canonical registry of Surface instances

A module-level `SURFACE_REGISTRY` SHALL be the canonical registry of Surface instances, keyed by `surface.name`. `register_surface(s)` SHALL reject duplicate names. `names()` SHALL return the registered surface names in insertion order. `get(name)` SHALL return the registered Surface or raise `KeyError`.

#### Scenario: Duplicate surface name rejected

- **GIVEN** an attempt to register two surfaces with `name = "api"`
- **WHEN** `SURFACE_REGISTRY.register_surface(...)` is called the second time
- **THEN** it raises with a duplicate-name error

### Requirement: Surfaces are passive — no import-time registry mutation

Every class implementing the `Surface` Protocol SHALL be passive: importing its defining module MUST NOT mutate any module-level or global registry. Surfaces SHALL be composed explicitly at `AppRuntime` build time (see `serve-topology`). The previous pattern where `packages/<surface>/__init__.py` called `SURFACE_REGISTRY.register_surface(...)` at import time is forbidden by this requirement.

#### Scenario: Importing a surface front door does not register it

- **GIVEN** a fresh interpreter
- **WHEN** code does `import a2kit.packages.mcp` (and nothing else from a2kit)
- **THEN** no registry — module-level or runtime-scoped — contains `McpSurface`
- **AND** the front door's top-level statements consist only of `import`s, the `__getattr__` lazy resolver, and `__all__`

#### Scenario: Architecture test enforces passivity

- **WHEN** the architecture suite (per `arch-fitness-functions`, when landed) inspects every `Surface`-Protocol class
- **THEN** each defining module's top-level AST contains no call expression that touches `SURFACE_REGISTRY` or any equivalent global

### Requirement: `DecoratorSurface[R]` template owns the shared registration shape

`DecoratorSurface[R]` SHALL be a generic Template class (R = the registration dataclass type) owning a `registrations: tuple[R, ...]` accumulator plus `_record(r)` helper for subclasses. `McpSurface` and `ApiSurface` SHALL extend `DecoratorSurface` with their concrete registration type; they SHALL NOT carry their own registration accumulators.

#### Scenario: Concrete surfaces inherit registrations from the template

- **GIVEN** `mcp = McpSurface()` and `api = ApiSurface()` extending `DecoratorSurface[...]`
- **WHEN** each registers one feature
- **THEN** `len(mcp.registrations) == 1` and `len(api.registrations) == 1` via the inherited accumulator
- **AND** neither subclass defines its own `registrations` field

### Requirement: `ToolDescriptor.expose` SHALL widen to `tuple[str, ...]`

`ToolDescriptor.expose` SHALL be `tuple[str, ...]` (not `tuple[Literal["mcp", "api"], ...]`). The `Literal["mcp", "api"]` typing SHALL be removed from the public descriptor surface. Decoration-time validation in `a2kit._verbs._validate_expose` SHALL reject unknown surface names with a `ValueError` naming the bundled set `{"mcp", "api"}`.

Registry-driven open-set validation against `SURFACE_REGISTRY.names()` is a follow-up: `_verbs` lives in the authoring layer (L2) and `SURFACE_REGISTRY` lives in dispatch (L4); reading the registry from L2 would violate `A2K-LAYER`. A future change will either relocate the registry to a lower layer or move expose validation into the runtime layer.

#### Scenario: Unknown expose name rejected at decoration

- **GIVEN** `@a2kit.read(expose=("mcp", "graphql"))`
- **WHEN** the decorator runs
- **THEN** a `ValueError` names `"graphql"` and lists the accepted set `{"mcp", "api"}`

#### Scenario: ToolDescriptor.expose type is open-set

- **WHEN** introspecting `ToolDescriptor.__annotations__["expose"]`
- **THEN** the type is `tuple[str, ...]`, not a `Literal` narrowing

### Requirement: `build_parent_app` SHALL mount surfaces via registry walk

`packages/serve.py:build_parent_app` SHALL walk `SURFACE_REGISTRY` instead of hardcoded `_has_api_registrations` / `_has_mcp_registrations` branches. For each surface with non-empty registrations on the active runtime, it SHALL call `surface.bind(runtime)` and mount the result at `/{surface.name}`. The hardcoded `_has_*` helpers SHALL be deleted.

The runtime currently surfaces only the bundled `api` / `mcp` accumulators (`runtime.api_surface` / `runtime.mcp_surface`), so registry-walk inspection of "has this surface any registrations?" still hits a bundled-only branch inside the helper. Third-party surface accumulators on the runtime are a follow-up; the registry-walk + mount path is already in place.

#### Scenario: Bundled surfaces mount via registry walk

- **GIVEN** a runtime with one `@a2kit.read` tool (default `expose=("mcp", "api")`)
- **WHEN** `build_parent_app(runtime)` runs
- **THEN** the resulting parent app mounts both `/mcp` and `/api`
- **AND** the mounts come from walking `SURFACE_REGISTRY` (no hardcoded `_has_*` branches remain in `serve.py`)

### Requirement: register_surface() side-effects into a kernel-layer name registry

`SURFACE_REGISTRY.register_surface(s)` SHALL, as a side-effect, append `s.name` to a kernel-layer (L0/L1) name registry exposed via `registered_surface_names() -> tuple[str, ...]`. The name registry MUST be importable from the `authoring` core sub-unit (L2) without violating the layer DAG. Duplicate-name registration MUST NOT add the name twice.

#### Scenario: Registering a surface populates the name registry

- **GIVEN** a fresh interpreter with no surfaces imported
- **WHEN** `a2kit.packages.mcp` and `a2kit.packages.http` are imported
- **THEN** `registered_surface_names()` returns a tuple containing `"mcp"` and `"api"` (in registration order)

#### Scenario: Name registry is layer-clean from authoring

- **WHEN** the lint rule `A2K-LAYER` is run against `src/a2kit/_verbs.py` (or wherever the verbs live)
- **AND** that file imports `registered_surface_names` from the kernel name-registry module
- **THEN** the lint rule reports no violation

#### Scenario: Duplicate registration does not duplicate the name

- **GIVEN** a Surface registered once
- **WHEN** `SURFACE_REGISTRY.register_surface(...)` is called again with the same name (which raises per existing spec)
- **THEN** `registered_surface_names()` still contains the name exactly once
- **AND** the duplicate-name error from the existing spec is unchanged

### Requirement: Future `Surface` implementations register via `PluginManifest`

Once `plugin-manifest` lands, every new `Surface`-Protocol implementation SHALL register via a `MANIFEST = PluginManifest(...)` constant in its package and SHALL be discovered through `load_surface(...)` at app boot. The imperative `SURFACE_REGISTRY.register_surface(...)` call path remains available for transitional purposes but SHALL NOT be the documented entry point for new surfaces.

The two existing surfaces (`mcp_surface`, `api_surface`) MAY remain on the imperative path until a separate migration change ports them — see BACKLOG entries "Port remaining extension surfaces to `PluginManifest`" and "`A2K-SURFACE-REGISTRY` lint rule" for the consolidated follow-up.

#### Scenario: New surface ships a MANIFEST

- **GIVEN** a new package `packages/<surface>/` adding a `Surface`-Protocol implementation
- **WHEN** the package's `__init__.py` is imported at boot
- **THEN** the surface is discovered via its `MANIFEST` constant (not via an imperative `register_surface(...)` call in user code)

#### Scenario: Lint rule binds against the manifest shape

- **WHEN** a `Surface`-Protocol class lands without an accompanying `MANIFEST` in the same package
- **THEN** the pytest-archon rule `A2K-SURFACE-REGISTRY` fails and names the missing manifest

