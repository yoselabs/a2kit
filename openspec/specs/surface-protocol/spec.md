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

`a2kit.packages.dispatch.surface` SHALL define a `runtime_checkable` `Surface` Protocol with: `name: ClassVar[str]`, `reserved_types: ClassVar[frozenset[type]]`, `substrate_dep_markers: ClassVar[frozenset[type]]`, `def bind(runtime, descriptors) -> Any`, `def install_di_bridge(runtime, substrate_app) -> None`. Substrate adapters (MCP, HTTP, future) SHALL satisfy this Protocol. The `Substrate = Literal["fastapi", "fastmcp"]` discriminator stays unchanged in this capability; its removal lives in `remove-substrate-literal`.

#### Scenario: McpSurface and ApiSurface satisfy Surface

- **WHEN** `isinstance(McpSurface(), Surface)` and `isinstance(ApiSurface(), Surface)` are evaluated
- **THEN** both return `True`

### Requirement: `SurfaceRegistry` is the canonical registry of Surface instances

A module-level `SURFACE_REGISTRY` SHALL be the canonical registry of Surface instances, keyed by `surface.name`. `register_surface(s)` SHALL reject duplicate names. `names()` SHALL return the registered surface names in insertion order. `get(name)` SHALL return the registered Surface or raise `KeyError`.

#### Scenario: Duplicate surface name rejected

- **GIVEN** an attempt to register two surfaces with `name = "api"`
- **WHEN** `SURFACE_REGISTRY.register_surface(...)` is called the second time
- **THEN** it raises with a duplicate-name error

#### Scenario: Bundled surfaces self-register at lazy front-door load

- **WHEN** `import a2kit.packages.mcp` and `import a2kit.packages.http` first run in a fresh interpreter
- **THEN** `SURFACE_REGISTRY.names()` contains both `"mcp"` and `"api"`

### Requirement: `DecoratorSurface[R]` template owns the shared registration shape

`DecoratorSurface[R]` SHALL be a generic Template class (R = the registration dataclass type) owning a `registrations: tuple[R, ...]` accumulator plus `_record(r)` helper for subclasses. `McpSurface` and `ApiSurface` SHALL extend `DecoratorSurface` with their concrete registration type; they SHALL NOT carry their own registration accumulators.

#### Scenario: Concrete surfaces inherit registrations from the template

- **GIVEN** `mcp = McpSurface()` and `api = ApiSurface()` extending `DecoratorSurface[...]`
- **WHEN** each registers one feature
- **THEN** `len(mcp.registrations) == 1` and `len(api.registrations) == 1` via the inherited accumulator
- **AND** neither subclass defines its own `registrations` field
