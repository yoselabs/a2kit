# connections-dispatch-hook — replace-surfaces-with-visibility delta

## MODIFIED Requirements

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
