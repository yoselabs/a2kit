# in-process-test-client — testing-client-wire-payload delta

## ADDED Requirements

### Requirement: Wire-encoded payload capture via call_wire

The `TestClient` SHALL expose an async method
`call_wire(tool_name, *, connection=None, **kwargs)` that dispatches
the tool identically to `invoke` and then returns the
formatter-encoded structured-content payload — byte-identical to
what an out-of-process MCP client would receive on the
`structuredContent` channel.

`call_wire` SHALL resolve the wire format by reading the tool
descriptor's cached `format_hint` (populated at registration time
per the `type-driven-format-routing` capability). `call_wire` SHALL
NOT re-run any type-inference heuristic and SHALL NOT accept an
explicit format-hint argument. The encoding pass SHALL go through
`a2kit.packages.formatter.format_response(value, format_hint=hint)`
and the returned payload SHALL be the `Response.data` field of the
formatter's result.

The dispatch path inside `call_wire` SHALL be the same one `invoke`
uses: DI resolution, decorator processing, tool body execution, and
all capture surfaces (`events`, `progress`, `logs`, `reports`) SHALL
populate exactly as they do for `invoke`.

`invoke` itself SHALL remain unchanged — it continues to return the
raw Python value the tool body produced, without a formatter pass.

#### Scenario: JSON-shaped return rendered as a dict

- **GIVEN** a tool annotated `-> Task` (single `BaseModel`) whose
  descriptor's `format_hint` resolves to `"json"`
- **WHEN** a test calls `await client.call_wire("tools.get_task",
  id="x")`
- **THEN** the returned value equals `task.model_dump(mode="json")`
  for the `task` the tool returned

#### Scenario: TSV-shaped return rendered as a TSV string

- **GIVEN** a tool annotated `-> list[Task]` where `Task` is
  scalar-only, whose descriptor's `format_hint` resolves to `"tsv"`
- **WHEN** a test calls `await client.call_wire("tools.list_tasks")`
- **THEN** the returned value is the TSV string produced by
  `encode_tsv` — header line in declared `Task.model_fields` order,
  one row per item, `\n` line terminator

#### Scenario: page-tsv return rendered as the JSON envelope

- **GIVEN** a tool annotated `-> Page[Task]` where `Task` is
  scalar-only, whose descriptor's `format_hint` resolves to
  `"page-tsv"`
- **WHEN** a test calls `await client.call_wire("tools.search")`
- **THEN** the returned value is the JSON-encoded string of the
  hybrid envelope `{"items": "<tsv>", "next_cursor": ...,
  "_items_format": "tsv", ...}` exactly as `encode_page_tsv`
  produces it

#### Scenario: auto-detected format matches production routing

- **GIVEN** two tools — one annotated `-> list[ScalarTask]` and one
  annotated `-> list[NestedTask]` (NestedTask has a list field) —
  registered on the same App
- **WHEN** a test calls `call_wire` on each
- **THEN** the first returns a TSV string and the second returns a
  JSON-shaped value (dict / list-of-dicts), reflecting the
  descriptor's cached `format_hint` for each tool

#### Scenario: capture surfaces populate on call_wire

- **GIVEN** a tool that calls `await event(ctx, "started")`, `await
  ctx.report_progress(1, total=2)`, and `await ldd.info(ctx,
  "halfway")` before returning
- **WHEN** a test calls `await client.call_wire(tool_name)`
- **THEN** `client.events`, `client.progress`, and `client.logs`
  contain the emitted entries in order — same shape as if the test
  had called `client.invoke`

#### Scenario: invoke returns the raw Python value unchanged

- **GIVEN** a tool annotated `-> list[ScalarTask]` whose descriptor
  routes to `"tsv"`
- **WHEN** a test calls `await client.invoke(tool_name)`
- **THEN** the returned value is the `list[ScalarTask]` the tool
  body returned — not a TSV string — confirming that adding
  `call_wire` did not change `invoke` semantics
