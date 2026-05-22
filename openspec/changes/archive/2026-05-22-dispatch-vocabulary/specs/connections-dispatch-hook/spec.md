## MODIFIED Requirements

### Requirement: Connection-string resolution runs at the dispatch hook seam

The dispatch hook installed by `install_connections(app, *conn_types)` SHALL perform wire-side conversion only: it converts the `connection: str` wire kwarg into typed `ConnectionConfig` instances and surfaces them as wire kwargs for the tool. The hook MUST NOT call `container.apply_kwargs` or perform DI chain resolution — DI is the framework's responsibility, layered on top of the hook's output by `Container.call_scope`.

The implementation of the hook-installation step lives in `a2kit.packages.connections.hook` (the function `install_connection_hook`); `install_connections` is the public entry point that wires the hook, the wire scope, and the CLI in one call.

#### Scenario: Hook returns wire-side resolved kwargs only

- **GIVEN** a tool `async def fetch(*, connection: TrackerConn) -> ...`
- **AND** `install_connections(app, TrackerConn)` ran
- **WHEN** the dispatch hook is invoked with `{"connection": "x"}`
- **THEN** the hook returns `{"connection": <TrackerConn instance>}`
- **AND** the hook does NOT call `container.apply_kwargs`
- **AND** any DI-resolved kwargs (e.g. `state: AppState`) come from the
  framework's `Container.resolve_params` step, not the hook

#### Scenario: Hook composes through `Container.call_scope(pre_hook=...)`

- **GIVEN** an App with a connection-aware tool and an app-scope `AppState` singleton
- **WHEN** the wrapper invokes `await app._resolver.call_scope(fn, wire, pre_hook=hook)`
- **THEN** the child container is opened
- **AND** the hook runs and yields wire-side resolved kwargs
- **AND** `child.resolve_params(fn)` runs for DI kwargs (Lazy[T] aware)
- **AND** wire and DI kwargs merge; the tool body runs inside the child's lifetime
- **AND** the child container's cleanup stack unwinds on exit
