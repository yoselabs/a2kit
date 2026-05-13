## MODIFIED Requirements

### Requirement: Per-parameter descriptions resolved from the docstring

The system SHALL extract per-parameter descriptions from the tool
function's docstring at decoration time and SHALL apply them to the
MCP parameter schema and CLI option help as if the parameter carried
`Annotated[T, pydantic.Field(description=...)]`. (The reference here
is to `pydantic.Field` rather than the historical `a2kit.Param` because
the sibling change `align-with-pydantic-and-stdlib` lands first and
collapses the Param wrapper into the underlying Pydantic field.)

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

The same WARN_ONCE-per-`__qualname__` contract SHALL apply to two additional decoration-time introspection sites that participate in describing or shaping the tool:

- The return-annotation copy in `_wrap_with_dispatch_hook` (`src/a2kit/packages/mcp/server.py`): when `get_type_hints(fn).get("return")` raises, the wrapped fn keeps its current (annotation-less) state — FastMCP receives no output schema for that tool, but decoration does not raise and one WARN is emitted per offender.
- The return-annotation resolution and selectable-fields derivation in `src/a2kit/tool.py` (`_resolve_return_annotation`, `_derive_selectable_fields`): when `get_type_hints(fn)` raises, the helpers return their documented fallback (`None` and `()` respectively); decoration does not raise; one WARN is emitted per offender via a module-local dedupe set.

The WARN_ONCE pattern SHALL mirror the existing pattern in `src/a2kit/signature.py:resolve_hints`: a single set tracking `__qualname__`, log emitted only on first failure per name in the process. Each module SHALL own its own dedupe set; cross-module sharing is not required.

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

#### Scenario: get_type_hints failure in docstring augmentation degrades with one warn-once log

- **GIVEN** a tool whose annotations cause `get_type_hints` to raise (e.g. an unresolved forward reference)
- **WHEN** `_augment_annotations_from_docstring` runs at decoration time
- **THEN** decoration SHALL NOT raise; the docstring augmentation is skipped for that tool
- **AND** a single WARN-level log line is emitted naming the tool's `__qualname__`
- **AND** subsequent decorations of the same `__qualname__` in the same process SHALL NOT emit a second line

#### Scenario: get_type_hints failure in return-annotation resolution degrades with one warn-once log

- **GIVEN** a tool whose annotations cause `get_type_hints` to raise
- **WHEN** `_resolve_return_annotation` is called during decoration (e.g. from `_check_return_scope` or `_derive_selectable_fields`)
- **THEN** the helper SHALL return `None`; decoration SHALL NOT raise
- **AND** one WARN-level log line is emitted naming the tool's `__qualname__`, scoped to a `tool.py`-local dedupe set
- **AND** a second decoration of the same `__qualname__` in the same process SHALL NOT emit a second line for the same site

#### Scenario: get_type_hints failure in selectable-fields derivation degrades with one warn-once log

- **GIVEN** a tool with a `list[T]` return annotation where `T` raises during `get_type_hints` resolution
- **WHEN** `_derive_selectable_fields` runs at decoration time
- **THEN** the helper SHALL return `()`; decoration SHALL NOT raise; the list-view `selectable_fields` falls back to empty
- **AND** one WARN-level log line is emitted naming the tool's `__qualname__`
- **AND** subsequent decorations of the same `__qualname__` in the same process SHALL NOT emit a second line for the same site

#### Scenario: Return-annotation copy in dispatch-hook wrapper degrades with one warn-once log

- **GIVEN** a tool whose annotations cause `get_type_hints` to raise during `_wrap_with_dispatch_hook`
- **WHEN** the MCP server constructs the wrapped fn for FastMCP registration
- **THEN** the wrapped fn SHALL NOT receive a copied `return` annotation; FastMCP's output schema for that tool is absent
- **AND** the wrap call SHALL NOT raise; tool registration completes
- **AND** one WARN-level log line is emitted naming the tool's `__qualname__`, scoped to an `mcp/server.py`-local dedupe set
- **AND** subsequent registrations of the same `__qualname__` in the same process SHALL NOT emit a second line

#### Scenario: Ignored parameter kinds

- **GIVEN** a tool whose docstring documents `ctx`, `self`, `*args`, or `**kwargs`
- **THEN** those entries SHALL be ignored even if present in the `Args:` block

#### Scenario: No bare suppress in decoration-time introspection paths

- **WHEN** the codebase is grepped under `src/a2kit/` for `contextlib.suppress(Exception)` or bare `except Exception:` in code reachable from tool decoration (including helpers in `tool.py`, `_docstring.py`, and `packages/mcp/server.py`'s `_wrap_with_dispatch_hook`)
- **THEN** every match SHALL either be the documented WARN_ONCE pattern or be justified in code-adjacent comment as not an introspection failure path
