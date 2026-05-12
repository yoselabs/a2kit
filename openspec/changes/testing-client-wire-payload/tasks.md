# Tasks — call_wire on the in-process test client

## 0. Prerequisites

- [ ] 0.1 Baseline: `make lint` and `make test` green at HEAD.
- [ ] 0.2 Confirm `descriptor.format_hint` is populated for every
      registered tool (already required by `type-driven-format-routing`
      → "Auto-format consults the cached descriptor hint"). Quick
      assertion in a throwaway script: every entry of
      `app.tool_descriptors()` has a non-None `format_hint` after
      registration.

## 1. Library — `src/a2kit/packages/testing/client.py`

- [ ] 1.1 Add `async def call_wire(self, tool_name: str, *,
      connection: str | None = None, **kwargs: Any) -> Any` on
      `TestClient`.
- [ ] 1.2 Implementation:
      1. `descriptor = self._descriptor(tool_name)`
      2. `value = await self.invoke(tool_name,
         connection=connection, **kwargs)`
      3. `response = format_response(value,
         format_hint=descriptor.format_hint)`
      4. `return response.data`
- [ ] 1.3 Verify the method docstring documents (a) return-type
      varies per format (dict for JSON, str for TSV / page-tsv),
      (b) capture surfaces still populate, (c) auto-detection uses
      the descriptor's cached hint.

## 2. Tests — `tests/test_in_process_client_wire.py` (new file)

- [ ] 2.1 Scenario "JSON return": tool annotated `-> Task` (single
      BaseModel). Assert `call_wire(...)` returns the dict
      `Task.model_dump(mode="json")` would produce.
- [ ] 2.2 Scenario "TSV return": tool annotated `-> list[Task]`
      where `Task` is scalar-only. Assert `call_wire(...)` returns
      the TSV string with header in declared field order, one row
      per item, `\n` line terminator.
- [ ] 2.3 Scenario "page-tsv return": tool annotated `-> Page[Task]`
      where `Task` is scalar-only. Assert `call_wire(...)` returns
      the JSON envelope string with `"_items_format": "tsv"` and
      embedded TSV `items` string.
- [ ] 2.4 Scenario "annotation flip changes wire format": two tools,
      one with `-> list[ScalarTask]` and one with
      `-> list[NestedTask]`. Assert `call_wire` returns TSV for the
      first and JSON for the second — using the same call site.
- [ ] 2.5 Scenario "capture surfaces populate": a tool that emits
      `event` + `report_progress` + `info` calls and returns a
      value. Assert `call_wire` returns the wire payload AND
      `client.events`, `client.progress`, `client.logs` all
      populated.
- [ ] 2.6 Scenario "invoke unchanged": same tool as 2.2; assert
      `await c.invoke(...)` still returns the `list[Task]` Python
      object, not the TSV string. Regression guard.

## 3. Docs

- [ ] 3.1 Update `src/a2kit/packages/testing/client.py` module
      docstring with a `call_wire` example next to the existing
      `render_as` example. Show the JSON-vs-TSV difference in two
      lines.
- [ ] 3.2 If the README has a "Testing tools" section that lists
      `invoke` / `render_as`, append a one-line `call_wire` entry.

## 4. Validation

- [ ] 4.1 `openspec validate testing-client-wire-payload --strict`
      passes.
- [ ] 4.2 `make lint` green.
- [ ] 4.3 `make test` green; the five new scenarios in 2.x land.

## 5. Downstream signal (out of scope for this change)

- [ ] 5.1 Note in the a2web feedback round-6 log that friction 2
      is unblocked: the ~5 stdio-harness tests can migrate to
      `client.call_wire(...)`. Migration itself happens in the
      a2web repo, not here.
