## MODIFIED Requirements

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

The resolved descriptions SHALL be stored on `A2KitMeta` as a
`param_descriptions: Mapping[str, str]` field so that no docstring
parsing happens per request and middleware can read the descriptions
without re-walking the function signature. The descriptions MAY also
be mirrored onto `fn.__annotations__` (carried inside the existing
`Annotated[...]` metadata for each parameter) so that downstream MCP
schema generators that read annotations directly continue to see the
descriptions. `A2KitMeta.param_descriptions` is the authoritative
surface; the annotation mirror is an implementation detail that the
spec permits but does not require any specific schema generator to
honour.

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

#### Scenario: Descriptions are stored on `A2KitMeta`

- **GIVEN** the `fetch` tool from the "Args section becomes parameter descriptions" scenario above
- **WHEN** the tool's `A2KitMeta` is read after decoration
- **THEN** `meta.param_descriptions` is a `Mapping[str, str]` with
  `meta.param_descriptions["url"] == "The absolute http(s) URL to fetch."`
- **AND** `meta.param_descriptions["timeout"] == "Seconds to wait before giving up."`
- **AND** reading `meta.param_descriptions` SHALL NOT re-parse the docstring
  (the field is populated once at decoration time)
