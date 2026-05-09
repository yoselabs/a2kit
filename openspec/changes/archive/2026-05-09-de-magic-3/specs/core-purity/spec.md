## ADDED Requirements

### Requirement: Core exposes only a typed dispatch hook protocol

`src/a2kit/*.py` (excluding `packages/`) SHALL define a single dispatch hook protocol consumed by tool dispatch, taking a tool function and a dict of wire kwargs and returning a dict of resolved kwargs. Core SHALL NOT import or reference `Container`, `ConnectionConfig`, `TrackerStore`, or any other concrete domain or DI type.

#### Scenario: Lint forbids container imports in core
- **WHEN** `A2K-CORE-CLEAN` scans `src/a2kit/routers.py`, `src/a2kit/tool.py`, `src/a2kit/__init__.py`, etc.
- **THEN** it reports any import of `a2kit.packages.connections.container.Container` or any reference to `ConnectionConfig` as a violation

#### Scenario: Hook protocol is the only DI surface in core
- **WHEN** the dispatch hook is defined
- **THEN** it appears as a `Protocol` with a single `__call__(fn, wire_kwargs) -> resolved_kwargs` shape and no other DI-related symbol exists in core

### Requirement: Apps without a Connections plugin get an identity hook

When an `App` has no provider registry (no `App.provide(...)` calls and no Connections plugin attached), the framework SHALL use an identity dispatch hook that returns `wire_kwargs` unchanged.

#### Scenario: Empty app builds and dispatches
- **GIVEN** an `App("demo")` with one router and zero `provide()` calls
- **WHEN** a tool is dispatched
- **THEN** the dispatch hook returns the wire kwargs unchanged
- **AND** no Container instance is constructed

### Requirement: A2KitMeta.extra remains the only extension point

Core's `A2KitMeta` dataclass SHALL retain `extra: dict[str, Any]` as the only namespaced extension carrier. The DI feature SHALL NOT add new fields to `A2KitMeta`. Any container-related per-tool data SHALL live in `meta.extra` under an `a2kit.di.*` key prefix.

#### Scenario: meta.extra carries injection-related metadata
- **GIVEN** the framework partitions a tool's kwargs at collect time
- **WHEN** the partition result is stored
- **THEN** it is written to `meta.extra["a2kit.di.partition"]` and not to a new field on `A2KitMeta`
