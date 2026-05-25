## ADDED Requirements

### Requirement: `Annotated[ReturnT, Raises(...)]` is the canonical typed-error form

The framework SHALL recognise the typed-error vocabulary of a tool, service method, or helper function exclusively through `typing.Annotated[ReturnT, Raises(...)]` on the return annotation. No decorator kwarg form (e.g. `@memory.read(raises=(...))`) SHALL be supported. Multiple `Raises(...)` markers in one `Annotated[...]` SHALL flatten additively (this composition rule is normative in `raises-annotation-contract`).

The framework SHALL strip the `Raises(...)` metadata before computing `format_hint` and serialization behavior. That is, `Annotated[Memory, Raises(NotFound)]` SHALL behave identically to `Memory` for the purposes of return-type discipline (BaseModel locality lint, format hint selection, page-detection).

#### Scenario: Annotated[Memory, Raises(...)] passes BaseModel locality lint

- **GIVEN** module-scope `class Memory(BaseModel): ...` and tool annotated `-> Annotated[Memory, Raises(NotFound)]`
- **WHEN** `A2K-LOCAL-RETURN-MODEL` runs
- **THEN** no `A2K-LOCAL-RETURN-MODEL` warning fires (Raises is invisible to the locality check)

#### Scenario: Annotated[list[Memory], Raises(...)] hits same locality lint as list[Memory]

- **GIVEN** in-function `class Memory(BaseModel): ...` and tool annotated `-> Annotated[list[Memory], Raises(NotFound)]`
- **WHEN** lint runs
- **THEN** `A2K-LOCAL-RETURN-MODEL` fires referencing the in-function `Memory`, just as it would for the bare `list[Memory]`

### Requirement: Cross-module closure verification reads helper `Raises` annotations

Service methods and helper functions called from tool bodies that declare `Annotated[T, Raises(...)]` on their return annotation SHALL be readable by the lint rule `A2K-RAISES-CLOSURE` to verify the calling tool's closure cross-module without walking helper bodies. The lint SHALL flatten the helper's `Raises` markers via `get_type_hints(include_extras=True)` exactly as for tools, and treat the resulting set as the helper's contributed raises at every call site.

When a helper does NOT carry `Raises(...)`, the lint SHALL fall back to AST walking of the call site only and SHALL NOT walk into the helper. A separate informational rule `A2K-RAISES-HELPER-UNTYPED` MUST warn the author at the call site (not at the helper definition) that closure verification for tools calling this helper will be best-effort, naming the helper.

#### Scenario: Helper with Raises supports cross-module closure check

- **GIVEN** `async def fetch_row(id: str) -> Annotated[Row, Raises(NotFound)]: ...`
- **AND** a tool body that calls `await fetch_row(id)` and declares `Raises(NotFound)`
- **WHEN** `A2K-RAISES-CLOSURE` runs
- **THEN** the lint reads `fetch_row`'s declared raises
- **AND** verifies the tool's declared raises cover the helper's raises
- **AND** no warning fires (closure verified cross-module)
