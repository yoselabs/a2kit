# raises-closure-lint Specification

## Purpose
TBD - created by archiving change a2effect-foundation. Update Purpose after archive.
## Requirements
### Requirement: `A2K-RAISES-CLOSURE` verifies declared raises cover the body

The lint rule `A2K-RAISES-CLOSURE` SHALL fire when a tool body (or service method body, when the method's return is `Annotated[T, Raises(...)]`) contains a `raise X(...)` statement where `X` is NOT in:

(a) the function's declared `Raises(...)` tuple, or
(b) caught and re-raised inside a `try / except` whose re-raise lands in the declared set, or
(c) covered by a registered enricher on the owning router or app whose output type is in the declared set.

The rule SHALL walk the body AST. It SHALL NOT walk into helper functions in v1 (transitive raise tracking is best-effort via the `raises_registry`; helpers carrying their own `Raises(...)` annotation are read cross-module).

The rule SHALL produce `LintMessage` with severity `error` (not warning). Strict mode is the only mode in v1.

#### Scenario: Body raise of undeclared type emits error

- **GIVEN** `Annotated[Memory, Raises(NotFound)]` on a tool
- **AND** the body contains `raise InvalidId("...")`
- **WHEN** lint runs
- **THEN** `A2K-RAISES-CLOSURE` fires at the `raise InvalidId(...)` line with severity `error`
- **AND** the message names the undeclared `InvalidId` and lists the declared set `(NotFound,)`

#### Scenario: Caught-and-re-raised type does not fire

- **GIVEN** `Annotated[Memory, Raises(InfrastructureError)]` on a tool
- **AND** body: `try: await db.get(...) except asyncpg.PostgresError as e: raise InfrastructureError(str(e)) from e`
- **WHEN** lint runs
- **THEN** no `A2K-RAISES-CLOSURE` message fires for this body

#### Scenario: Enricher-covered raise does not fire

- **GIVEN** `Annotated[Memory, Raises(InfrastructureError)]` on a tool
- **AND** a router enricher `def f(exc: asyncpg.PostgresError) -> InfrastructureError | None`
- **AND** body raises `asyncpg.PostgresError` via `raises_as` mapping or directly
- **WHEN** lint runs
- **THEN** no `A2K-RAISES-CLOSURE` fires (translation chain covers the raise)

### Requirement: `A2K-RAISES-UNCOVERED` flags registry-known throwers without coverage

The lint rule `A2K-RAISES-UNCOVERED` SHALL fire when a tool body contains a call expression to a function listed in the `raises_registry` whose declared raise type is NOT covered by:

(a) the function's declared `Raises(...)` tuple,
(b) an explicit `try / except` block enclosing the call,
(c) an enricher path that produces a type in the declared set, or
(d) a `# a2effect: defect-ok` annotation on the line.

The rule SHALL produce `LintMessage` with severity `warning` by default (uncovered calls are not strictly wrong but indicate a likely missing translation).

#### Scenario: httpx call without coverage warns

- **GIVEN** the registry entry `httpx.AsyncClient.get -> httpx.RequestError | httpx.HTTPStatusError`
- **AND** a tool body containing `await client.get(url)` with no try/except and no enricher covering httpx errors
- **AND** the tool's declared raises do not include httpx errors via an enricher path
- **WHEN** lint runs
- **THEN** `A2K-RAISES-UNCOVERED` warning fires at the call site naming `client.get` and the registry-declared raises

#### Scenario: defect-ok annotation suppresses the warning

- **GIVEN** the same setup as above
- **AND** the call line carries `# a2effect: defect-ok`
- **WHEN** lint runs
- **THEN** no `A2K-RAISES-UNCOVERED` warning fires for that line

### Requirement: `A2K-RAISES-NOT-TYPED` rejects non-AppError members

The lint rule `A2K-RAISES-NOT-TYPED` SHALL fire when a `Raises(...)` marker contains a type that is not a subclass of `AppError`. The rule SHALL produce `LintMessage` with severity `error`.

#### Scenario: Raises with raw asyncpg type fires

- **GIVEN** an annotation `Annotated[Memory, Raises(asyncpg.PostgresError)]`
- **WHEN** lint runs
- **THEN** `A2K-RAISES-NOT-TYPED` fires at the annotation naming `asyncpg.PostgresError`
- **AND** the message instructs the author to subclass `AppError` or register an enricher

### Requirement: Lint rules ship via Python entry points

The a2effect package SHALL declare its lint rules under the `a2lint.rules` entry-point group in its `pyproject.toml`:

```toml
[project.entry-points."a2lint.rules"]
"A2K-RAISES-CLOSURE" = "a2effect._lint:raises_closure_rule"
"A2K-RAISES-UNCOVERED" = "a2effect._lint:raises_uncovered_rule"
"A2K-RAISES-NOT-TYPED" = "a2effect._lint:raises_not_typed_rule"
```

The a2effect package SHALL NOT depend on any specific lint runner. Any conforming runner that discovers entry points under `a2lint.rules` SHALL be able to load and execute the rules. In v1, the rules are also runnable via a built-in CLI shim `python -m a2effect.lint <path>` to enable adoption before any external runner ships.

Lint rules SHALL use stdlib `ast` only in v1 (no `libCST` dependency). Autofix capability via libCST is deferred to a follow-up change.

#### Scenario: pip-installing a2effect exposes rules under entry-points

- **GIVEN** `pip install a2effect`
- **WHEN** `importlib.metadata.entry_points(group="a2lint.rules")` is enumerated
- **THEN** the three rules `A2K-RAISES-CLOSURE`, `A2K-RAISES-UNCOVERED`, `A2K-RAISES-NOT-TYPED` are present
- **AND** each entry's `.load()` returns a callable rule object

#### Scenario: Built-in CLI shim runs without external runner

- **GIVEN** a2effect installed and no external lint runner
- **WHEN** the user runs `python -m a2effect.lint src/myapp/`
- **THEN** the shim discovers the entry-point rules
- **AND** runs them across all `.py` files under `src/myapp/`
- **AND** prints lint messages to stdout
- **AND** exits 0 if no errors, non-zero otherwise

