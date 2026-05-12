# tool-description-contract — param-docstring-pull delta

## ADDED Requirements

### Requirement: Per-parameter descriptions resolved from the docstring

The system SHALL extract per-parameter descriptions from the tool
function's docstring at decoration time and SHALL apply them to the
MCP parameter schema and CLI option help as if the parameter carried
`Annotated[T, a2kit.Param(description=...)]`.

The supported docstring format is **Google-style only**. A
parameter section is introduced by a line whose stripped content is
one of `Args:`, `Arguments:`, or `Parameters:` (case-insensitive,
trailing colon required). The section ends at the next blank-then-
non-indented line, the next recognised Google section header
(`Returns:`, `Raises:`, `Yields:`, `Examples:`, `Note:`, `Notes:`,
`Attributes:`, `See Also:`), or the end of the docstring.

Each entry within the section has the shape
`name: description` or `name (type): description`. The optional
`(type)` SHALL be discarded — types come from the signature.
Continuation lines (indented further than the entry line) SHALL be
joined with a single space.

The resolved descriptions SHALL be stored on `A2KitMeta` (e.g. a
`param_descriptions: Mapping[str, str]` field) so that no docstring
parsing happens per request.

#### Scenario: Args section becomes parameter descriptions

- **GIVEN** a tool

  ```python
  @a2kit.read()
  async def fetch(*, url: str, timeout: int = 30) -> Result:
      """Fetch content from a URL.

      Args:
          url: The absolute http(s) URL to fetch.
          timeout: Seconds to wait before giving up.
      """
  ```

- **THEN** the MCP input schema has
  `properties.url.description == "The absolute http(s) URL to fetch."`
- **AND** `properties.timeout.description == "Seconds to wait before giving up."`
- **AND** `<app> fetch --help` shows the same strings for `--url` and `--timeout`

#### Scenario: Arguments and Parameters aliases are accepted

- **GIVEN** a tool whose docstring uses `Arguments:` (or `Parameters:`) instead of `Args:`
- **THEN** the parameter descriptions are resolved identically to the `Args:` form

#### Scenario: Type suffix is discarded

- **GIVEN** a docstring entry `url (str): The URL.`
- **THEN** the resolved description for `url` is `"The URL."` with no `(str)` prefix

#### Scenario: Continuation lines join with a single space

- **GIVEN** a docstring entry

  ```
  url: The absolute http(s) URL
      to fetch from.
  ```

- **THEN** the resolved description for `url` is `"The absolute http(s) URL to fetch from."`

#### Scenario: Section ends at the next recognised header

- **GIVEN** a docstring whose `Args:` block is followed by `Returns:`
- **THEN** lines under `Returns:` SHALL NOT be treated as parameter descriptions

#### Scenario: Malformed docstring degrades silently

- **GIVEN** a docstring with no `Args:` section (or a malformed one)
- **WHEN** the tool is decorated
- **THEN** decoration SHALL NOT raise; affected parameters fall back to "no description"

#### Scenario: Ignored parameter kinds

- **GIVEN** a tool whose docstring documents `ctx`, `self`, `*args`, or `**kwargs`
- **THEN** those entries SHALL be ignored even if present in the `Args:` block

### Requirement: Explicit Param or Field description wins over the docstring

The system SHALL prefer an explicit `Annotated[T, FieldInfo(description=...)]`
description over any docstring `Args:` entry for the same parameter name,
and SHALL fall back to the docstring entry only when the explicit
description is `None` or absent. Resolution order, first hit wins:

1. Explicit `Annotated[T, FieldInfo(description=...)]` — covers both
   `a2kit.Param(description=...)` and bare `pydantic.Field(description=...)`.
2. Google-style docstring `Args:` entry for that parameter name.
3. No description.

Both forms of `a2kit.Param` description — keyword
(`Param(description="x")`) and positional shorthand (`Param("x")`) —
SHALL participate in step 1.

The conflict SHALL be resolved silently. No warning, no debug log,
no decoration-time error when both sources are present and disagree.

#### Scenario: Explicit Param wins over docstring

- **GIVEN** a tool

  ```python
  @a2kit.read()
  async def fetch(
      *,
      url: Annotated[str, a2kit.Param(description="Explicit override.")],
  ) -> Result:
      """Fetch content.

      Args:
          url: From the docstring.
      """
  ```

- **THEN** the MCP input schema's `properties.url.description == "Explicit override."`
- **AND** no warning is emitted at decoration time

#### Scenario: Bare pydantic Field description wins over docstring

- **GIVEN** the same tool but with `Annotated[str, pydantic.Field(description="Field override.")]`
- **THEN** the MCP input schema's `properties.url.description == "Field override."`

#### Scenario: Docstring wins when Param carries no description

- **GIVEN** a tool

  ```python
  @a2kit.read()
  async def fetch(
      *,
      url: Annotated[str, a2kit.Param(examples=["https://x"])],
  ) -> Result:
      """Fetch content.

      Args:
          url: From the docstring.
      """
  ```

- **THEN** the MCP input schema's `properties.url.description == "From the docstring."`
- **AND** `properties.url.examples == ["https://x"]`

#### Scenario: No description when neither source supplies one

- **GIVEN** a tool with no `Annotated` metadata on `url` and no `Args:` entry for `url`
- **THEN** the MCP input schema's `properties.url` has no `description` key

### Requirement: No new third-party dependency is introduced

The docstring resolver SHALL be implemented in-tree (hand-rolled,
~30 LOC) using `inspect.cleandoc` and standard library primitives.
`docstring-parser`, `griffe`, and similar packages SHALL NOT be added
to `pyproject.toml` for this capability.

#### Scenario: pyproject.toml carries no new docstring dependency

- **WHEN** this change lands
- **THEN** `pyproject.toml` `[project] dependencies` SHALL NOT include
  `docstring-parser`, `griffe`, or any equivalent docstring-parsing library

### Requirement: Non-goal — Numpy / Sphinx / reST docstring styles

The system SHALL NOT parse Numpy-style (`Parameters\n----------\n...`),
Sphinx / reST field-list (`:param name:`), or any mixed-style
parameter blocks for this contract. Authors using those styles SHALL
continue to use `a2kit.Param(description=...)` for per-parameter
descriptions.

#### Scenario: Numpy-style block is not parsed

- **GIVEN** a tool whose docstring uses a Numpy-style `Parameters`
  block with a `----------` underline
- **THEN** the resolver SHALL NOT extract per-parameter descriptions
  from it; affected parameters fall back to "no description" unless an
  explicit `Param` or `Field` description is present

#### Scenario: Sphinx :param: field list is not parsed

- **GIVEN** a tool whose docstring uses `:param url: ...` field-list
  entries
- **THEN** those entries SHALL NOT be extracted as parameter descriptions
