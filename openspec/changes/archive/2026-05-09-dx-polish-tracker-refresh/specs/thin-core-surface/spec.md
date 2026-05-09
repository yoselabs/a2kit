## MODIFIED Requirements

### Requirement: `App.connect` registers a connection class with optional store binding

`App.connect(conn_type: type[ConnT], *, store: type | None = None) -> App`
SHALL register `conn_type` as a known connection. When `store` is
provided, it SHALL be registered as the canonical store class for that
connection — both `Depends(conn_type)` and `Depends(store)` resolve
through the registered store.

`app.get_store(conn_type)` continues to return the `ConnectionStore`
backing instance for `conn_type` (used to load a connection by name);
this is the loader, not the user-facing store class.

#### Scenario: connect without store
- **WHEN** `app.connect(TrackerConn)` is called (no `store` kwarg)
- **THEN** `app.connection_types()` includes `TrackerConn`; `app.get_store(TrackerConn)` returns the loader; `Depends(TrackerStore)` requires explicit `TrackerStore.conn_type` binding

#### Scenario: connect with store kwarg
- **WHEN** `app.connect(TrackerConn, store=TrackerStore)` is called
- **THEN** `Depends(TrackerStore)` resolves via the loader registered under `TrackerConn`

#### Scenario: connect remains chainable
- **WHEN** `app.connect(C, store=S).connect(D, store=T).use(R())` is invoked
- **THEN** the chain returns the App and both connections + stores are registered
