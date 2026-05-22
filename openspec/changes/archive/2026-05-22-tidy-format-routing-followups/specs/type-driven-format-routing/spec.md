## MODIFIED Requirements

### Requirement: `format_response` accepts `"tsv"` and `"page-tsv"` as first-class hints

`format_response(raw, *, format_hint)` SHALL accept `format_hint` values `"auto"`, `"json"`, `"tsv"`, and `"page-tsv"`. `"toon"` is not an accepted value. Explicit hints SHALL bypass type inference and dispatch directly to the corresponding encoder.

#### Scenario: Explicit `"tsv"` honored on a list of scalar-only models
- **GIVEN** `raw = [Task(...), Task(...)]`
- **WHEN** `format_response(raw, format_hint="tsv")` is called
- **THEN** the response data is the output of `encode_tsv` and `Response.format` is `"tsv"`

#### Scenario: Explicit `"page-tsv"` honored on a Page
- **GIVEN** `raw = Page[Task](items=[...], next_cursor="x")`
- **WHEN** `format_response(raw, format_hint="page-tsv")` is called
- **THEN** the response data is the output of `encode_page_tsv` and `Response.format` is `"json"` (the wire format is JSON; `_items_format` discriminates)

### Requirement: Auto-format consults the cached descriptor hint

When `format_hint="auto"` is passed to `format_response` from `_invoke_tool_in_process`, the runtime SHALL pass the descriptor's pre-computed `format_hint` instead of re-running any heuristic. No `toon_or_json` heuristic is invoked — the helper no longer exists.

#### Scenario: Tool with `-> list[Task]` (scalar-only) → TSV at runtime
- **GIVEN** an app with a tool annotated `-> list[Task]` (scalar-only) and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool and formats the response
- **THEN** the wire output is TSV (matches `encode_tsv` byte-for-byte)

#### Scenario: Tool with `-> Page[Task]` (scalar-only) → page-tsv at runtime
- **GIVEN** an app with a tool annotated `-> Page[Task]` and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool
- **THEN** the wire output is the hybrid JSON-with-embedded-TSV

#### Scenario: Tool with `-> Task` (single) → JSON at runtime
- **GIVEN** an app with a tool annotated `-> Task` and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool
- **THEN** the wire output is JSON

#### Scenario: Tool without annotation → JSON at runtime
- **GIVEN** an app with a tool that has no return annotation
- **WHEN** the user invokes the CLI with `--format auto`
- **THEN** the wire output is JSON
