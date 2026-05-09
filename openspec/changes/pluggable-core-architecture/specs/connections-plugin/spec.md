## ADDED Requirements

### Requirement: `Connections` plugin owns connection registration

`a2kit.packages.connections.Connections` SHALL be a class implementing
the `Plugin` Protocol. Its responsibilities:

- `register(app)` — caches the App, marks the plugin as the canonical
  conn-class registry.
- `claim(thing) → True` for any class subclass of `ConnectionConfig`.
- `adopt(conn_class, app)` — adds the class to its internal
  `_conn_types: list[type]`.
- `cli_commands() → [connections_group]` — the existing
  `connections login/logout/list/show/delete` Click group.
- `depends_resolvers() → [conn_resolver, store_resolver]` — handles
  `Depends(<conn_class>)` and `Depends(<store_class>)`.

The plugin does NOT contribute tool wrappers — enricher application
remains a Router responsibility (see `thin-core-surface`).

The plugin owns its registry — the App does not have
`_connection_types` anymore.

#### Scenario: Connections registers and claims conn classes
- **WHEN** `app.use(Connections())` then `app.use(TrackerConn)` runs
- **THEN** the `Connections` instance has `TrackerConn` in its registry; the App has no direct knowledge

#### Scenario: connections CLI subcommand only present when plugin loaded
- **WHEN** an App has no `Connections()` plugin and `<app> --help` is invoked
- **THEN** no `connections` subgroup appears in help output

#### Scenario: connections CLI subcommand present when plugin loaded
- **WHEN** `app.use(Connections())` runs and the CLI is built
- **THEN** `<app> connections login`, `logout`, `list`, `show`, `delete` are available

### Requirement: Connection-specific exceptions live in the plugin package

The exceptions `ConnectionKwargMissing`, `ConnectionNotRegistered`,
`StoreConnectionTypeUnknown` SHALL live in
`a2kit.packages.connections.exceptions`, NOT in `a2kit.exceptions`.
They SHALL NOT be lazy-exported from `a2kit`.

#### Scenario: Import path
- **WHEN** code does `from a2kit.packages.connections import ConnectionNotRegistered`
- **THEN** the import succeeds

#### Scenario: Old import path raises
- **WHEN** code does `from a2kit import ConnectionNotRegistered` (legacy)
- **THEN** `AttributeError` is raised — these symbols no longer live on the core namespace

### Requirement: `Store[ConnT]` marker lives in the connections package

`a2kit.Store` SHALL be removed from the core namespace. Stores that
participate in the connections DI live under
`a2kit.packages.connections.Store`. Authors import from there.

#### Scenario: Store import path
- **WHEN** a store class is declared as `class TrackerStore(a2kit.packages.connections.Store[TrackerConn]):`
- **THEN** the runtime resolves `Depends(TrackerStore)` exactly as before

### Requirement: Backwards-compat sugar for `App.connect(...)`

`App.connect(conn_class)` SHALL continue to work — but ONLY when a
`Connections` plugin is already registered. The implementation:

```python
def connect(self, conn_class):
    plugin = self._find_plugin(Connections)
    if plugin is None:
        raise RuntimeError(
            "App.connect() requires the Connections plugin. "
            "Did you forget `app.use(Connections())`?"
        )
    plugin.adopt(conn_class, self)
    return self
```

This keeps existing code working, while making the dependency
explicit. New code SHOULD use `app.use(Connections()).use(ConnClass)`.

#### Scenario: connect with plugin loaded
- **WHEN** `app.use(Connections()); app.connect(TrackerConn)` runs
- **THEN** TrackerConn is registered identically to `app.use(TrackerConn)`

#### Scenario: connect without plugin raises with hint
- **WHEN** `app.connect(TrackerConn)` is called on an App that has no `Connections` plugin
- **THEN** `RuntimeError` is raised with a message naming the missing plugin
