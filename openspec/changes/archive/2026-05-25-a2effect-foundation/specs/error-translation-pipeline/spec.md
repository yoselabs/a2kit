## ADDED Requirements

### Requirement: Translation chain order is fixed and deterministic

When a tool body raises an exception, the framework SHALL attempt translation in this fixed order, stopping at the first match that returns a non-None result:

1. **Inline helpers** (`raises_as(coro, mapping)`, `translate_to(target, *sources)` context manager) wrapping the call site that raised.
2. **Router enrichers** registered on the tool's owning `Router` via `@router.enricher`, in registration order.
3. **App enrichers** registered on the `App` via `@app.enricher`, in registration order.
4. **Defect quarantine** — anything that escapes layers 1-3 SHALL be wrapped in `UnexpectedDefect(original)`.

Order is not configurable. The first translation that returns a non-None `AppError` wins; subsequent layers SHALL NOT be tried.

#### Scenario: Router enricher fires before app enricher

- **GIVEN** a router with an enricher translating `asyncpg.PostgresError -> InfrastructureError("db")`
- **AND** the app has an enricher translating `Exception -> AppError("generic")`
- **WHEN** a tool body raises `asyncpg.PostgresError`
- **THEN** the wire envelope's `type == "InfrastructureError"` (router won, app never called)

#### Scenario: Inline translate_to fires before router enricher

- **GIVEN** a router enricher translating `asyncpg.PostgresError -> InfrastructureError`
- **AND** the tool body runs `async with translate_to(SpecificError, asyncpg.PostgresError): await db.get(...)`
- **WHEN** the call raises `asyncpg.PostgresError`
- **THEN** the wire envelope's `type == "SpecificError"`

#### Scenario: Unhandled raises hit defect quarantine

- **GIVEN** no enricher and no inline handler covers `RuntimeError`
- **WHEN** a tool body raises `RuntimeError("bug")`
- **THEN** the wire envelope's `type == "UnexpectedDefect"`, `kind == "bug"`

### Requirement: `@router.enricher` decorator with wide and narrow forms

The `@router.enricher` decorator SHALL accept callables of two forms, both with return type `AppError | None`:

- **Wide form**: `def f(exc: Exception) -> AppError | None`. Framework calls for every exception; author matches inside.
- **Narrow form**: `def f(exc: <SpecificException>) -> AppError | None`. Framework reads the first parameter annotation at registration; calls only when `isinstance(exc, <SpecificException>)`.

Type checkers (pyright, mypy, TY) SHALL reject enricher functions whose return type is not `AppError | None` (or a subclass union thereof) at definition time without requiring any plugin.

Enrichers registered via `@router.enricher` SHALL replace the previous class-level `enrichers: tuple[Callable[[Exception], str | None], ...]` attribute on `Router`. The class-level attribute SHALL be removed; defining it SHALL raise `TypeError` at class-creation time directing the author to use the decorator.

The same shape and rules SHALL apply to `@app.enricher` registered on the `App`.

#### Scenario: Narrow enricher only fires on isinstance match

- **GIVEN** `@memory.enricher\ndef _pg(exc: asyncpg.PostgresError) -> InfrastructureError | None: return InfrastructureError(str(exc))`
- **WHEN** the tool raises `httpx.HTTPStatusError` (not a PostgresError)
- **THEN** `_pg` is NOT called
- **AND** translation falls through to the next layer

#### Scenario: Wide enricher fires for every exception

- **GIVEN** `@memory.enricher\ndef _all(exc: Exception) -> AppError | None: ...`
- **WHEN** the tool raises any exception
- **THEN** `_all` is called once
- **AND** if it returns None, translation continues to the next layer

#### Scenario: Class-level enrichers attribute is rejected

- **GIVEN** `class MyRouter(Router): enrichers = (some_fn,)`
- **WHEN** the class body is evaluated
- **THEN** a `TypeError` is raised at class-creation time
- **AND** the message directs the author to `@router.enricher`

### Requirement: `raises_as(coro, mapping)` is the primary inline helper

`a2effect.raises_as` SHALL accept a coroutine (or awaitable) and a mapping `dict[type[Exception], type[AppError] | Callable[[Exception], AppError]]`. On `await`, the framework SHALL execute the awaitable; if it raises an exception whose type matches a key in the mapping, the framework SHALL translate to the mapped value:

- If the value is a `type[AppError]`, the framework SHALL construct `target(str(original))` with `__cause__` set to the original.
- If the value is a callable, the framework SHALL call `target(original)` and raise the result.

If no key matches, the original exception SHALL propagate unchanged (translation falls through to the enricher chain).

#### Scenario: Mapping translates raised type

- **GIVEN** `row = await raises_as(db.get(id), {asyncpg.NoData: NotFound})`
- **WHEN** `db.get(id)` raises `asyncpg.NoData("...")`
- **THEN** the call raises `NotFound("...")`
- **AND** `__cause__` is the original `asyncpg.NoData`

#### Scenario: Callable value receives the original exception

- **GIVEN** `await raises_as(c, {ValueError: lambda e: InvalidId(str(e), details={"raw": e.args})})`
- **WHEN** `c` raises `ValueError("bad")`
- **THEN** the resulting `InvalidId.details == {"raw": ("bad",)}`

#### Scenario: Unmatched exception propagates

- **GIVEN** `await raises_as(c, {ValueError: NotFound})`
- **WHEN** `c` raises `RuntimeError("x")`
- **THEN** `RuntimeError` propagates unchanged for downstream translation

### Requirement: `translate_to(target, *sources)` is the multi-statement context-manager helper

`a2effect.translate_to(target: type[AppError], *sources: type[Exception])` SHALL return an async context manager. Within the `async with` block, any exception whose type is a subclass of any `source` SHALL be re-raised as `target(str(original)) from original`. Exceptions of unrelated types SHALL propagate unchanged.

#### Scenario: Multi-statement translation within block

- **GIVEN** `async with translate_to(InfrastructureError, asyncpg.PostgresError):\n    row = await db.get(id)\n    other = await db.query(...)`
- **WHEN** either call raises any `asyncpg.PostgresError` subclass
- **THEN** the block re-raises `InfrastructureError(str(original))` from `original`
