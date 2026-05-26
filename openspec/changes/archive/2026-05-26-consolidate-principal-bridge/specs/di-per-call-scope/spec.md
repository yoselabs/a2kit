## MODIFIED Requirements

### Requirement: Dispatcher opens and closes a per-call scope around each tool invocation

The dispatcher SHALL open a per-call child container scope around
each tool invocation via `Container.call_scope` (or
`container.child()` directly). Inside that scope, per-call typed
instances are published via the explicit `seed_scoped(type_, value)`
API on the child. The previous implicit "values in `wire_kwargs`
become SCOPED providers by type" behaviour is removed.

`wire_kwargs` is, again, a literal dict of named values passed
into `pre_hook` and matched by name to the target function's
parameters. It SHALL NOT trigger any DI side effects.

#### Scenario: Tool body resolves a SCOPED dep seeded via the explicit API

- **GIVEN** a tool body declaring `principal: Principal`
- **AND** a child container with `seed_scoped(Principal, p)` called
  before `call_scope` resolution
- **WHEN** the body is dispatched through `call_scope`
- **THEN** the body receives `p` as its `principal` kwarg

#### Scenario: wire_kwargs does NOT auto-seed by value type

- **GIVEN** `await container.call_scope(fn, {"opaque": SomeInstance()})`
  where `fn` declares no parameter named `opaque` and no parameter
  typed `SomeInstance`
- **WHEN** the scope opens
- **THEN** `SomeInstance` is NOT registered as a SCOPED provider on
  the child
- **AND** `child.has_provider(SomeInstance)` is `False`

#### Scenario: wire_kwargs named values still flow by parameter name

- **GIVEN** `await container.call_scope(fn, {"name": "alice"})` and
  `fn(self, *, name: str) -> ...`
- **WHEN** the scope opens and `merged` is yielded
- **THEN** `merged["name"] == "alice"`
- **AND** no DI registration was created for `str`

### Requirement: pre_hook contract: hooks receive an explicit seed callable

`pre_hook` SHALL have the signature
`Callable[[fn, wire_kwargs, seed], dict | Awaitable[dict]]`.
The third argument `seed` is a callable
`(type_: type, value: Any) -> None` that publishes a typed instance
on the child container as a SCOPED provider for the per-call scope.

Hooks that need to publish a typed result (e.g., a connection
instance derived from a connection-string wire value) MUST call
`seed(T, instance)` before returning the merged dict. Hooks that
have nothing to publish ignore the `seed` parameter.

#### Scenario: pre_hook publishes a typed instance via seed

- **GIVEN** a `pre_hook` that resolves `"conn_name"` into a
  `TrackerConn` instance
- **WHEN** the hook calls `seed(TrackerConn, resolved_conn)` and
  returns `{"connection": resolved_conn}`
- **THEN** `child.has_provider(TrackerConn)` is `True`
- **AND** a downstream factory declaring `conn: TrackerConn`
  receives `resolved_conn` from the child container

#### Scenario: pre_hook signature is enforced

- **GIVEN** a `pre_hook` callable accepting only two positional
  arguments
- **WHEN** the dispatcher invokes the hook with the new three-arg
  signature
- **THEN** a clear `TypeError` is raised at the call site naming the
  required signature
