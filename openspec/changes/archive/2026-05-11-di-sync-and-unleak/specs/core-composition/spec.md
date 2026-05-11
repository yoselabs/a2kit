## MODIFIED Requirements

### Requirement: `App.container()` returns the active container

The `App` class SHALL eager-initialize a `Container` instance during `App.__init__` and SHALL expose `container() -> Container` returning that instance. The return type is non-`Optional`. The `_ensure_container` lazy path is removed.

#### Scenario: Container available immediately after App construction

- **WHEN** `app = App("name")` is constructed and `app.container()` is called
- **THEN** the return value is a `Container` instance
- **AND** the call site is not required to check for `None`

#### Scenario: Single container instance across an App's lifetime

- **WHEN** `app.container()` is called twice on the same `App` instance
- **THEN** both calls return the same object
