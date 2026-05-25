## ADDED Requirements

### Requirement: `ToolDescriptor.raises` field carries declared error vocabulary

`ToolDescriptor` SHALL gain a new field `raises: tuple[type[AppError], ...]` populated by reading `Raises(...)` markers from the tool function's return annotation at registration time. The framework SHALL use `typing.get_type_hints(fn, include_extras=True)` and walk `__metadata__` on `Annotated[...]` types to extract all `Raises` instances, flattening their `types` tuples into a deduplicated ordered tuple stored on the descriptor.

When the return annotation is bare (no `Annotated`) or contains no `Raises(...)` metadata, `descriptor.raises` SHALL be the empty tuple `()`.

The `descriptor.return_type` field SHALL continue to hold the bare return type (the first argument to `Annotated`), unchanged in semantics by the presence of `Raises(...)`.

#### Scenario: Tool with Raises populates the descriptor

- **GIVEN** `@memory.read\nasync def fetch(*, id: str) -> Annotated[Memory, Raises(NotFound, InvalidId)]: ...`
- **WHEN** the router is added to the app
- **THEN** `descriptor.raises == (NotFound, InvalidId)`
- **AND** `descriptor.return_type is Memory`
- **AND** `descriptor.format_hint` is computed from `Memory` as before (Raises does not affect format selection)

#### Scenario: Tool without Annotated has empty raises

- **GIVEN** `@memory.read\nasync def now() -> str: return "ok"`
- **WHEN** registered
- **THEN** `descriptor.raises == ()`

#### Scenario: Multiple Raises markers flatten into descriptor

- **GIVEN** a return annotation `Annotated[Memory, Raises(NotFound), Raises(InvalidId)]`
- **WHEN** descriptor materializes
- **THEN** `descriptor.raises` contains both `NotFound` and `InvalidId` (order may match declaration; set membership is what matters)

### Requirement: Descriptor materialization rejects non-AppError members in Raises

When a `Raises(...)` marker contains a type that is not a subclass of `AppError`, descriptor materialization SHALL raise `TypeError` naming the offending type and the tool function. The error message SHALL direct the author to subclass `AppError` or use an enricher.

This is the runtime backstop to the `A2K-RAISES-NOT-TYPED` build-time lint rule; both should produce the same diagnostic for the same condition.

#### Scenario: Raw exception in Raises raises at registration

- **GIVEN** `Annotated[Memory, Raises(asyncpg.PostgresError)]` on a tool function
- **WHEN** the router is added to the app
- **THEN** `TypeError` is raised at registration naming `asyncpg.PostgresError` and the tool function name
