## MODIFIED Requirements

### Requirement: Auto format selection runs against the normalized payload

When `format_hint="auto"` is passed to `format_response`, the encoder SHALL be selected via the cached `format_hint` on the calling tool's `ToolDescriptor`. `format_response` itself, when called outside of a tool dispatch context (no descriptor available), SHALL fall back to `"json"`. The previous behavior — running `toon_or_json` on the normalized payload to choose between TOON and JSON — is retired. `toon_or_json` and `encode_toon` are removed entirely; passing `format_hint="toon"` SHALL raise `ValueError`.

#### Scenario: Auto in tool dispatch reads the descriptor
- **GIVEN** a tool whose descriptor has `format_hint="tsv"`
- **WHEN** `_invoke_tool_in_process` formats the tool's return value under `--format auto`
- **THEN** the encoder dispatched is `encode_tsv`

#### Scenario: Auto in tool dispatch for a Page-returning tool
- **GIVEN** a tool annotated `-> Page[Task]` (scalar-only `Task`) whose descriptor has `format_hint="page-tsv"`
- **WHEN** `_invoke_tool_in_process` formats the return value under `--format auto`
- **THEN** the encoder dispatched is `encode_page_tsv` (JSON envelope with embedded TSV)

#### Scenario: Auto outside dispatch context falls back to JSON
- **GIVEN** a direct call `format_response(raw, format_hint="auto")` from user code (no descriptor in scope)
- **WHEN** the call is evaluated
- **THEN** the response is JSON-encoded

#### Scenario: TOON is unsupported
- **GIVEN** legacy code calling `format_response(raw, format_hint="toon")`
- **WHEN** the call is evaluated
- **THEN** a `ValueError` is raised explaining that TOON is removed and pointing to `"tsv"` / `"json"` / `"page-tsv"`
