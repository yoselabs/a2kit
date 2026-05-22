## MODIFIED Requirements

### Requirement: Routers declare enrichers via class attribute and/or `enrich` method

Routers SHALL declare exception enrichers using a class attribute `enrichers: tuple[Callable[[Exception], str | None], ...]` and/or an instance method `def enrich(self, exc: Exception) -> str | None`. There is no stacked `@enriches(...)` decorator.

#### Scenario: Class-list enrichers

- **GIVEN** `class TasksRouter(a2kit.Router): slug = "tasks"; enrichers = (generic_404, tracker_404)`
- **WHEN** a tool on this router raises an exception
- **THEN** the framework calls `generic_404(exc)` first; if it returns `None`, calls `tracker_404(exc)`; the first non-None result is used as the user-facing message

#### Scenario: Instance method takes precedence

- **GIVEN** a router defines both `enrichers = (fallback,)` and `def enrich(self, exc): ...`
- **WHEN** a tool raises an exception
- **THEN** `self.enrich(exc)` is invoked first; if it returns `None`, the class tuple is walked

#### Scenario: Empty enrichers tuple is the default

- **GIVEN** a router that declares neither `enrichers` nor `enrich`
- **WHEN** a tool on this router raises an exception
- **THEN** no enrichment runs and the raw exception message reaches the transport

### Requirement: Router tool methods may rely on the docstring for parameter descriptions

The framework SHALL accept per-parameter descriptions sourced from a Google-style `Args:` block in the docstring of any router tool method (any method decorated with `@a2kit.read`, `@a2kit.write`, or `@a2kit.list_`), and SHALL apply them to the MCP input schema and CLI option help per the `tool-description-contract` capability when no explicit pydantic `Field` description is present on the parameter. Router authors MAY therefore omit `Annotated[T, Field(description=...)]` wrappers whose only content is a description that already appears in the docstring.

Router authors SHOULD prefer the docstring when a parameter's only schema metadata is its description, and SHOULD keep an explicit `Field(...)` when the parameter also carries non-description metadata (`examples=`, `ge=`, `le=`, `title=`, etc.) or when the description must differ from the docstring entry.

#### Scenario: Router tool with docstring-only descriptions

- **GIVEN** a router

  ```python
  class FetchRouter(a2kit.Router):
      @a2kit.read()
      async def fetch(self, *, url: str, timeout: int = 30) -> Result:
          """Fetch a URL.

          Args:
              url: Absolute http(s) URL.
              timeout: Seconds to wait.
          """
  ```

- **WHEN** the router is added to an `App`
- **THEN** the registered tool's MCP input schema has
  `properties.url.description == "Absolute http(s) URL."` and
  `properties.timeout.description == "Seconds to wait."`
- **AND** the corresponding click subcommand's option help shows the
  same strings

#### Scenario: Router tool mixing docstring and explicit Field

- **GIVEN** a router tool whose `url` parameter uses
  `Annotated[str, Field(examples=["https://x"])]` and whose
  docstring `Args:` has `url: Absolute http(s) URL.`
- **THEN** the resulting MCP schema for `url` carries both the
  description (from the docstring) and the examples (from the `Field`)

#### Scenario: Self and ctx are not described from the docstring

- **GIVEN** a router method whose docstring `Args:` block documents
  `self` or `ctx`
- **THEN** those entries are ignored and do not affect the registered
  tool's MCP input schema

## REMOVED Requirements

### Requirement: `Router.lifespan` classmethod surface SHALL be removed

**Reason**: ADR 0018 — a living capability spec describes only the current surface and must not cite a removed symbol in backticks. The pre-v0.35 `lifespan` classmethod is gone; router lifecycle is already fully specified by the requirements "Routers SHALL express lifecycle via `__aenter__` / `__aexit__`" and "Router lifecycle SHALL fire lazily on first dispatch". The drift gate flags the dead dotted citation; documenting absence is no longer a spec concern.

**Migration**: Router authors implement the async context manager protocol (`async def __aenter__`/`async def __aexit__`) on the Router subclass instance. See the `__aenter__`/`__aexit__` lifecycle requirements in this same capability for the canonical surface.
