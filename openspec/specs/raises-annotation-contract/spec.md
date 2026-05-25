# raises-annotation-contract Specification

## Purpose
TBD - created by archiving change a2effect-foundation. Update Purpose after archive.
## Requirements
### Requirement: `Raises(*types)` marker is the canonical error vocabulary surface

A tool's, service method's, or helper function's error vocabulary SHALL be declared via `typing.Annotated[ReturnT, Raises(E1, E2, ...)]` on the return annotation. `Raises` SHALL be a frozen `dataclass(frozen=True, slots=True)` exported from `a2effect`, accepting a variadic positional sequence of `type[AppError]`.

`Raises(...)` SHALL NOT be a decorator kwarg; no `@memory.read(raises=(...))` form exists. Authoring the contract on the decorator and on the annotation in conflict SHALL raise `TypeError` at tool registration.

`Raises(...)` SHALL carry zero per-call runtime cost. The framework reads it at tool registration via `typing.get_type_hints(fn, include_extras=True)` and caches the result on the `ToolDescriptor`.

#### Scenario: Tool with Annotated return + Raises registers cleanly

- **GIVEN** `@memory.read\nasync def fetch(*, id: str) -> Annotated[Memory, Raises(NotFound, InvalidId)]: ...`
- **WHEN** the router is added to the app
- **THEN** the resulting `ToolDescriptor.raises == (NotFound, InvalidId)`
- **AND** `ToolDescriptor.return_type == Memory` (bare, with Raises stripped)

#### Scenario: Tool without Annotated return has empty raises

- **GIVEN** `@memory.read\nasync def now() -> str: return "ok"`
- **WHEN** registered
- **THEN** the descriptor's `raises` tuple is empty

### Requirement: Multiple `Raises` markers compose additively

When a return annotation carries multiple `Raises(...)` metadata entries in the same `Annotated[...]` bracket, the framework SHALL flatten them into the union of all declared types. Ordering of markers SHALL be irrelevant.

This enables composition: a helper function carries its own `Raises(...)` annotation, and a tool that wraps the helper can declare both the helper's raises and its own by listing both markers.

#### Scenario: Two Raises markers in one Annotated flatten

- **GIVEN** a return annotation `Annotated[Memory, Raises(NotFound), Raises(InvalidId)]`
- **WHEN** the descriptor materializes
- **THEN** `descriptor.raises == (NotFound, InvalidId)` (order may match declaration but set membership is what matters)

#### Scenario: Order of metadata is irrelevant

- **GIVEN** `Annotated[Memory, Raises(NotFound), Body(...)]` and `Annotated[Memory, Body(...), Raises(NotFound)]`
- **WHEN** both are processed
- **THEN** both yield identical `raises` tuples
- **AND** FastAPI's `Body(...)` interpretation is preserved in both cases

### Requirement: `Raises(...)` accepts only `AppError` subclasses

The framework SHALL reject `Raises(...)` markers containing non-`AppError` types at tool registration. The lint rule `A2K-RAISES-NOT-TYPED` SHALL also catch this at build time.

Raw third-party exceptions (`asyncpg.PostgresError`, `httpx.HTTPStatusError`) SHALL be translated to an `AppError` subclass via an enricher or inline helper (`raises_as`, `translate_to`); they SHALL NOT appear directly in `Raises(...)`.

#### Scenario: Raises with non-AppError raises at registration

- **GIVEN** `@memory.read\nasync def fetch(...) -> Annotated[Memory, Raises(asyncpg.PostgresError)]: ...`
- **WHEN** the router is added to the app
- **THEN** registration raises `TypeError` naming the offending type
- **AND** the message instructs the author to either subclass `AppError` or register an enricher

### Requirement: `Raises(...)` composes with other `Annotated` metadata cleanly

`Raises(...)` SHALL coexist with FastAPI markers (`Body`, `Query`, `Path`, `Depends`, `Security`) and pydantic markers (`Field`) on the same `Annotated[...]` bracket without interference in either direction. The framework reads only its own metadata via `isinstance(m, Raises)` filtering; other libraries' metadata is left untouched.

#### Scenario: Annotated[Memory, Body(embed=True), Raises(NotFound)] preserves both behaviours

- **GIVEN** a tool with `id: Annotated[str, Body(embed=True), Field(min_length=1)]` parameter and `-> Annotated[Memory, Raises(NotFound)]` return
- **WHEN** the tool is mounted on FastAPI via `build_http_app`
- **THEN** the FastAPI route binds `id` from the request body
- **AND** pydantic enforces `min_length=1` on the id
- **AND** the descriptor's `raises == (NotFound,)`
- **AND** OpenAPI schema renders for the tool without error

