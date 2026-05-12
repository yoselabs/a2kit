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

The resolved descriptions SHALL be stored on `A2KitMeta` (e.g. a
`param_descriptions: Mapping[str, str]` field) so that no docstring
parsing happens per request.

The docstring-pull path SHALL NOT use bare `contextlib.suppress(Exception)` to silence parse failures or `get_type_hints` failures. Instead, both sites (the docstring parser in `src/a2kit/_docstring.py` and the `get_type_hints` call in `_augment_annotations_from_docstring` inside `src/a2kit/tool.py`) SHALL catch the exception, log one WARN-level line per offender (deduped by `fn.__qualname__` via a module-local `_WARN_ONCE: set[str]`), and continue with the documented fallback (empty descriptions / no augmentation). Decoration SHALL NOT raise on docstring parse or hint-resolution failure — the semantic outcome (silent degrade for the affected tool) is unchanged; only the silence is replaced with a single observable log line per offender.

The WARN_ONCE pattern SHALL mirror the existing pattern in `src/a2kit/signature.py:resolve_hints`: a single set tracking `__qualname__`, log emitted only on first failure per name in the process.

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

#### Scenario: Malformed docstring degrades with one warn-once log

- **GIVEN** a tool whose docstring parser raises on a malformed `Args:` block
- **WHEN** the tool is decorated
- **THEN** decoration SHALL NOT raise; the affected parameters fall back to "no description"
- **AND** a single WARN-level log line is emitted naming the tool's `__qualname__`
- **AND** decorating the same tool a second time in the same process SHALL NOT emit a second log line (dedupe by `__qualname__`)

#### Scenario: get_type_hints failure degrades with one warn-once log

- **GIVEN** a tool whose annotations cause `get_type_hints` to raise (e.g. an unresolved forward reference)
- **WHEN** `_augment_annotations_from_docstring` runs at decoration time
- **THEN** decoration SHALL NOT raise; the docstring augmentation is skipped for that tool
- **AND** a single WARN-level log line is emitted naming the tool's `__qualname__`
- **AND** subsequent decorations of the same `__qualname__` in the same process SHALL NOT emit a second line

#### Scenario: Ignored parameter kinds

- **GIVEN** a tool whose docstring documents `ctx`, `self`, `*args`, or `**kwargs`
- **THEN** those entries SHALL be ignored even if present in the `Args:` block
