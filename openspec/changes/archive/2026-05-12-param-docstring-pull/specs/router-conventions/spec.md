# router-conventions — param-docstring-pull delta

## ADDED Requirements

### Requirement: Router tool methods may rely on the docstring for parameter descriptions

The framework SHALL accept per-parameter descriptions sourced from a
Google-style `Args:` block in the docstring of any router tool
method (any method decorated with `@a2kit.read`, `@a2kit.write`,
`@a2kit.tool`, or `@a2kit.list_`), and SHALL apply them to the MCP
input schema and CLI option help per the `tool-description-contract`
capability when no explicit `Param`/`Field` description is present
on the parameter. Router authors MAY therefore omit
`Annotated[T, a2kit.Param(description=...)]` wrappers whose only
content is a description that already appears in the docstring.

Router authors SHOULD prefer the docstring when a parameter's only
schema metadata is its description, and SHOULD keep
`a2kit.Param(...)` when the parameter also carries non-description
metadata (`examples=`, `ge=`, `le=`, `title=`, etc.) or when the
description must differ from the docstring entry.

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

#### Scenario: Router tool mixing docstring and explicit Param

- **GIVEN** a router tool whose `url` parameter uses
  `Annotated[str, a2kit.Param(examples=["https://x"])]` and whose
  docstring `Args:` has `url: Absolute http(s) URL.`
- **THEN** the resulting MCP schema for `url` carries both the
  description (from the docstring) and the examples (from `Param`)

#### Scenario: Self and ctx are not described from the docstring

- **GIVEN** a router method whose docstring `Args:` block documents
  `self` or `ctx`
- **THEN** those entries are ignored and do not affect the registered
  tool's MCP input schema
