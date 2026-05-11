## ADDED Requirements

### Requirement: Connection-string resolution runs at the dispatch hook seam

The connections package SHALL provide a factory that builds an async dispatch hook resolving `wire_kwargs["connection"]` to a typed `ConnectionConfig` instance via the registered `ConnectionStore`. Substitution happens before the DI container resolves any other kwarg. The container itself SHALL NOT receive a `connection` keyword and SHALL NOT know about the `"connection"` name.

#### Scenario: Hook awaits store load and substitutes

- **GIVEN** an app with `Connections.install(app, ConnConfig)` and a tool method declaring `cfg: ConnConfig`
- **WHEN** the tool is dispatched with wire kwargs `{"connection": "prod"}`
- **THEN** the dispatch hook awaits `store.load("prod")`, substitutes the resulting `ConnConfig` into wire kwargs under the parameter name `cfg`, removes `"connection"` from the wire dict
- **AND** then calls `container.apply_kwargs(fn, wire_kwargs)` synchronously to fill any remaining injectables

#### Scenario: No connection, hook falls through

- **GIVEN** a connection-aware app
- **WHEN** a tool with no `ConnConfig` dependency is dispatched and `"connection"` is not in wire kwargs
- **THEN** the hook does not await the store
- **AND** the call falls through to `container.apply_kwargs(fn, wire_kwargs)` synchronously

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
