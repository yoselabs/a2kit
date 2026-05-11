## ADDED Requirements

### Requirement: DI container lives at `a2kit.packages.di`

The synchronous DI container module SHALL live at `src/a2kit/packages/di/container.py`. The file at `src/a2kit/packages/connections/container.py` SHALL NOT exist. All other a2kit modules that need container types or functions SHALL import from `a2kit.packages.di`, not from `a2kit.packages.connections`.

#### Scenario: Container module is importable without connections

- **WHEN** a script imports `a2kit.packages.di.container` in an environment where `a2kit.packages.connections` is not used
- **THEN** the import succeeds and the `Container` class is available

#### Scenario: Old import path is gone

- **WHEN** a script tries `from a2kit.packages.connections.container import Container`
- **THEN** the import fails with `ModuleNotFoundError` or equivalent

### Requirement: Container references no feature names

The container module SHALL NOT contain any reference (in code, docstrings, or attribute names) to features built on top of it. Specifically: no `"connection"`, no `_chain_reaches_connection`, no `needs_connection`, no `install_connection_providers`.

#### Scenario: Source grep for feature names

- **WHEN** the source of `a2kit/packages/di/` is grepped for `"connection"`, `"tracker"`, `"tenant"`, or any other feature-suggestive string
- **THEN** no matches are found except in docstrings that explicitly enumerate "this container has no feature awareness" as the contract

### Requirement: Public surface is small and synchronous

The container's public surface SHALL consist of: `Container` class with `register`, `has`, `providers`, `resolve`, `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`. Plus the exception `UnresolvableType`. All methods SHALL be synchronous. The `container_dispatch` async helper that previously wrapped `apply_kwargs` is replaced by a sync `container_dispatch_sync` (or `apply_kwargs` is used directly).

#### Scenario: All resolve paths are sync

- **WHEN** `inspect.iscoroutinefunction(Container.resolve)` is checked
- **THEN** the result is `False`

#### Scenario: No async surface

- **WHEN** the container's public method set is enumerated
- **THEN** no method is `async def`
