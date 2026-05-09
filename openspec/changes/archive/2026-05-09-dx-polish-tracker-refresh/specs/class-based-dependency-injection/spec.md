## ADDED Requirements

### Requirement: `Depends(<connection-class>)` resolves through the registered store

When a tool kwarg has `Depends(ConnT)` where `ConnT` is a class registered
via `app.connect(ConnT)`, the runtime SHALL resolve the dependency by:

1. Reading the `connection: str` kwarg from the tool's call kwargs.
2. Looking up the store for `ConnT` via `app.get_store(ConnT)`.
3. Calling `store.load(connection)` and substituting the result into the
   tool's `conn` kwarg.

If the tool signature has no `connection: str` kwarg, the resolver SHALL
raise `ConnectionKwargMissing` at call time. If `ConnT` is not registered,
the resolver SHALL raise `ConnectionNotRegistered`. Both errors are tool-
body errors (visible to the agent as a normal tool error envelope).

#### Scenario: Single connection class registered, tool depends directly
- **WHEN** `app.connect(TrackerConn)` is called and a tool body declares `conn: TrackerConn = Depends(TrackerConn), connection: str`
- **THEN** invoking the tool with `connection="default"` injects `store.load("default")` as `conn`

#### Scenario: Connection kwarg missing
- **WHEN** the tool signature has `Depends(TrackerConn)` but no `connection: str` kwarg
- **THEN** `ConnectionKwargMissing` is raised at first invocation

#### Scenario: Connection class not registered
- **WHEN** the tool depends on `Depends(SomeConn)` and `app.connect(SomeConn)` was never called
- **THEN** `ConnectionNotRegistered` is raised at first invocation

### Requirement: `Depends(<store-class>)` constructs `Store(conn)` automatically

When a tool kwarg has `Depends(StoreT)` where `StoreT` declares its
connection type (via class attribute `conn_type: type[ConnT]` OR as
`Generic[ConnT]` with a single bound type parameter), the runtime SHALL:

1. Resolve the connection via the same path as
   `Depends(<connection-class>)` above.
2. Instantiate `StoreT(resolved_conn)` and substitute as the kwarg value.

The store class SHALL be cheap to construct — the runtime makes a fresh
instance per call. Authors who need pooling or caching SHALL implement
that inside the store, not at the DI layer.

#### Scenario: Store with class-attribute conn_type
- **WHEN** `class TrackerStore: conn_type = TrackerConn` and a tool declares `store: TrackerStore = Depends(TrackerStore)`
- **THEN** the runtime injects `TrackerStore(loaded_conn)` per call

#### Scenario: Store with Generic conn type
- **WHEN** `class TrackerStore(Store[TrackerConn]):` and a tool declares `store: TrackerStore = Depends(TrackerStore)`
- **THEN** the runtime resolves `TrackerConn` via the Generic parameter and injects `TrackerStore(loaded_conn)`

#### Scenario: Store class without conn binding raises
- **WHEN** `Depends(StoreT)` is declared but `StoreT` neither sets `conn_type` nor inherits from `Store[ConnT]`
- **THEN** `StoreConnectionTypeUnknown` is raised at decoration time (before any tool call)

### Requirement: `app.connect(ConnT, *, store=None)` accepts an optional store class

`App.connect` SHALL accept an optional `store: type | None` kwarg. When
set, the runtime SHALL register `StoreT` as the canonical store for
`ConnT` AND set `StoreT.conn_type = ConnT` if not already set
(idempotent). This is sugar for the common case "one store per
connection class."

#### Scenario: connect with store kwarg
- **WHEN** `app.connect(TrackerConn, store=TrackerStore)` is called
- **THEN** subsequent `Depends(TrackerStore)` resolves to `TrackerStore(loaded_conn)` even if `TrackerStore.conn_type` was not explicitly set

#### Scenario: connect without store kwarg keeps legacy behavior
- **WHEN** `app.connect(TrackerConn)` is called (no store)
- **THEN** `Depends(TrackerConn)` works as before; `Depends(TrackerStore)` requires `TrackerStore.conn_type` to be set explicitly

### Requirement: Stub-function pattern remains supported

Legacy `Depends(get_conn)` (where `get_conn` is a stub identity function)
+ `app.use_factory(...)` SHALL continue to work without change. This
change is purely additive — no path is removed.

#### Scenario: Legacy pattern unchanged
- **WHEN** an existing tool uses `*, conn: TrackerConn = Depends(get_conn)` with `app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)`
- **THEN** the tool continues to work identically; no warning or deprecation fires
