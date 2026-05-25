# raises-registry Specification

## Purpose
TBD - created by archiving change a2effect-foundation. Update Purpose after archive.
## Requirements
### Requirement: Built-in stubs cover the common Python async ecosystem

The `a2effect.raises_registry` module SHALL ship built-in stub data describing the exception types raised by common third-party libraries. Coverage in v1 SHALL include at minimum:

- `httpx` — `AsyncClient.get/post/put/delete/patch/request/send`, raising `httpx.RequestError | httpx.HTTPStatusError | httpx.TimeoutException`.
- `asyncpg` — `Connection.execute/fetch/fetchrow/fetchval`, `Pool.acquire`, raising `asyncpg.PostgresError` (and subclasses).
- `redis.asyncio` — `Redis.get/set/del/exists/expire`, raising `redis.RedisError | redis.ConnectionError | redis.TimeoutError`.
- `sqlalchemy` — `AsyncSession.execute/scalar/scalars`, raising `sqlalchemy.exc.SQLAlchemyError` (and common subclasses).
- `fastapi` — `HTTPException` (already typed; included for completeness when reading from FastAPI-internal code).

Stubs SHALL be data-only (JSON or similar) and SHALL NOT import the third-party libraries themselves. `import a2effect.raises_registry` SHALL load the data without triggering `import httpx`, `import asyncpg`, etc.

#### Scenario: Lookup for known-thrown function returns declared raises

- **WHEN** `raises_registry.get("httpx.AsyncClient.get")` is called
- **THEN** the result is a frozenset containing the strings `"httpx.RequestError"`, `"httpx.HTTPStatusError"`, `"httpx.TimeoutException"`

#### Scenario: Unknown function returns empty

- **WHEN** `raises_registry.get("some.unknown.func")` is called
- **THEN** the result is an empty frozenset

#### Scenario: Importing registry does not pull stub-targeted libraries

- **WHEN** `import a2effect.raises_registry` runs in a fresh interpreter
- **THEN** `httpx`, `asyncpg`, `redis`, `sqlalchemy` are absent from `sys.modules`

### Requirement: pyproject.toml extension mechanism

Consumers SHALL extend the registry via their `pyproject.toml`:

```toml
[tool.a2effect.raises_registry]
"mymodule.MyClient.fetch" = ["mymodule.FetchError", "httpx.TimeoutException"]
"mymodule.MyClient.create" = ["mymodule.ConflictError", "mymodule.FetchError"]
```

At lint-rule load time, the registry SHALL merge built-in stubs with consumer extensions. Consumer extensions SHALL take precedence on key collision (consumer's keys override built-ins for that exact function path).

#### Scenario: pyproject extension merges with builtins

- **GIVEN** a project with the above `[tool.a2effect.raises_registry]`
- **WHEN** the lint runs over that project
- **THEN** `raises_registry.get("mymodule.MyClient.fetch")` returns `frozenset({"mymodule.FetchError", "httpx.TimeoutException"})`
- **AND** built-in entries like `"httpx.AsyncClient.get"` are still resolvable

### Requirement: Inline annotation mechanism

Authors writing helper functions SHALL be able to declare may-raise sets inline via a comment-based annotation:

```python
class MyClient:
    async def fetch(self, url: str) -> dict:
        # a2effect: may-raise FetchError, httpx.TimeoutException
        ...
```

The annotation SHALL be:

- A single line starting with `# a2effect: may-raise ` (exact prefix, lowercase).
- Comma-separated list of fully qualified exception type names (or bare names resolvable in the function's module scope).
- Placed inside the function body, anywhere (the lint walks AST and resolves the function's enclosing scope).

The lint rule SHALL prefer inline annotations over registry data when both are present for the same function.

#### Scenario: Inline annotation is read by the lint

- **GIVEN** a helper as above with `# a2effect: may-raise FetchError, httpx.TimeoutException`
- **AND** a tool that calls `await client.fetch(...)` without coverage of `FetchError`
- **WHEN** lint runs
- **THEN** `A2K-RAISES-UNCOVERED` warning fires naming `FetchError` and `httpx.TimeoutException` as the uncovered set

### Requirement: Pydantic ValidationError default enricher

The a2effect package SHALL ship a default enricher `a2effect.enrichers.pydantic_validation_error_enricher` that translates `pydantic.ValidationError` into `a2effect.InputError` with `details.fields` carrying the pydantic error list (each entry: `{loc, msg, type, input}`).

The enricher SHALL be opt-in via `app.enricher(pydantic_validation_error_enricher)` so consumers who handle pydantic validation differently are not surprised. The enricher SHALL be importable without triggering `import pydantic` if pydantic is not installed (lazy import inside the function body).

#### Scenario: Registered enricher translates pydantic ValidationError

- **GIVEN** `app.enricher(pydantic_validation_error_enricher)` is called during app setup
- **AND** a tool body that runs `MyModel.model_validate(bad_input)` raising `pydantic.ValidationError`
- **WHEN** the tool is invoked
- **THEN** the wire envelope's `type == "InputError"`, `kind == "input"`
- **AND** `details.fields` is a list of pydantic error dicts (loc, msg, type, input)

