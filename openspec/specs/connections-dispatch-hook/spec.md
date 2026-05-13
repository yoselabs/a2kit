# connections-dispatch-hook Specification

## Purpose
TBD - created by archiving change di-sync-and-unleak. Update Purpose after archive.
## Requirements
### Requirement: Connection-string resolution runs at the dispatch hook seam

The `install_connections(app, *conn_types)` function SHALL be the
single public entry point for plugin consumers. It MUST install the
dispatch hook, register the wire scope on the container, AND
register the CLI subcommand group via `app.add_cli(...)`. The
standalone `connections_cli(...)` factory SHALL NOT be exported
from `a2kit.packages.connections.__all__`.

#### Scenario: One-call wiring
- **GIVEN** a plugin consumer writing `install_connections(app, TrackerConn)` (and nothing else)
- **WHEN** the App's CLI is built
- **THEN** `<app> connections login --help` works
- **AND** the dispatch hook resolves `connection: str` → `TrackerConn` correctly
- **AND** the wire scope `"connection"` is registered on the container

#### Scenario: `connections_cli` removed from public surface
- **WHEN** `from a2kit.packages.connections import connections_cli`
- **THEN** the import succeeds (the symbol remains internally accessible) but it is absent from `__all__`
- **AND** documentation directs authors to `install_connections` only

### Requirement: The string `"connection"` lives only in the connections package

The literal `"connection"` SHALL appear only in `src/a2kit/packages/connections/` (and in tests that exercise connections behavior). It SHALL NOT appear in `src/a2kit/app.py`, `src/a2kit/packages/di/`, or any other module.

#### Scenario: Source grep audit

- **WHEN** the literal string `"connection"` is searched across `src/a2kit/`
- **THEN** matches occur only under `src/a2kit/packages/connections/`

### Requirement: Apps without Connections retain the sync container dispatch

The default `app._dispatch_hook` for apps that never call `Connections.install(app, ...)` SHALL be a thin sync wrapper around `container.apply_kwargs`. No async wrap, no per-call coroutine overhead for connection-less apps.

#### Scenario: Connection-less app dispatch

- **GIVEN** an app with `app.singleton(AppState, build_state)` and no `Connections.install` call
- **WHEN** a tool is dispatched
- **THEN** `app._dispatch_hook` returns a dict (not an awaitable), and the runtime invokes it without `await`

