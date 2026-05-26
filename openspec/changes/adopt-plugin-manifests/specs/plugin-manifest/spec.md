## ADDED Requirements

### Requirement: `PluginManifest[T]` is the framework's declarative extension-point shape

a2kit SHALL provide a private framework module `a2kit.packages._plugin` exposing four names: `PluginManifest`, `Unavailable`, `load_surface`, and `load_surface_sorted`. `PluginManifest[T]` SHALL be a frozen dataclass with fields `name: str`, `protocol: type[T]`, `factory: Callable[..., T | Unavailable]`, `requires: tuple[str, ...] = ()`, `settings_prefix: str | None = None`, and `priority: int = 0`. Each plugin file SHALL export exactly one `MANIFEST` constant of this type.

#### Scenario: Manifest fields round-trip

- **GIVEN** `MANIFEST = PluginManifest(name="foo", protocol=P, factory=lambda s: Foo(), priority=10)` in a discoverable module
- **WHEN** `load_surface(path, P, settings)` runs
- **THEN** the returned dict contains `{"foo": Foo()}` and the manifest's priority is preserved for sorted variants

### Requirement: `Unavailable` drops a plugin before it reaches the registry

A factory SHALL return `Unavailable(reason)` (a `NamedTuple` with one string field) when its capability is missing at boot (no API key, no credentials, no optional dependency). `load_surface` SHALL silently drop any plugin whose factory returns `Unavailable`, logging one INFO line per drop with the surface, plugin name, and reason. The registry returned to the caller SHALL contain only available plugins.

#### Scenario: Unavailable plugin is absent from the registry

- **GIVEN** a manifest whose factory returns `Unavailable("ANTHROPIC_API_KEY missing")`
- **WHEN** `load_surface(...)` runs
- **THEN** the returned dict does NOT contain the plugin's name
- **AND** a structured INFO log line records `event="plugin_unavailable"`, `name=<plugin>`, `reason="ANTHROPIC_API_KEY missing"`

#### Scenario: Unavailable is never raised as an exception

- **WHEN** any plugin factory determines it cannot construct
- **THEN** the factory returns `Unavailable(reason)`
- **AND** the factory does NOT raise

### Requirement: Manifest modules are side-effect-free at import time

Every module exporting a `MANIFEST` constant SHALL declare only the protocol implementation, the factory, and the manifest constant. Top-level side effects (network calls, env reads, mutation of any registry) are forbidden, because `load_surface` imports every module under the discovered surface path at boot.

#### Scenario: Architecture test enforces the invariant

- **WHEN** the architecture suite runs over every manifest-bearing surface path
- **THEN** each module's top-level AST contains only import statements, dataclass / function definitions, and the `MANIFEST` assignment

### Requirement: `load_surface_sorted` returns plugins in descending priority order

`load_surface_sorted(path, protocol, context) -> list[tuple[str, T]]` SHALL discover manifests the same way as `load_surface` and return `[(name, instance), ...]` sorted by descending `priority`. Negative priorities (`-1`) SHALL appear last; they signal "out-of-band" plugins dispatched by explicit name rather than iteration.

#### Scenario: Priority ordering is deterministic

- **GIVEN** three manifests with priorities `10, 5, -1`
- **WHEN** `load_surface_sorted(...)` runs
- **THEN** the result order is `[priority=10, priority=5, priority=-1]`
