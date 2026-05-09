## Context

`a2kit/packages/cli/runtime.py::_invoke_tool_in_process` does roughly:

```python
raw = await fn(**kwargs)
response = format_response(raw, format_hint=...)
```

`format_response` lives in `a2kit/packages/formatter/__init__.py` and dispatches to `_encode_json` (uses `json.dumps(..., default=str)`) or `encode_toon` (calls `toon_format.normalize`). Neither understands pydantic `BaseModel`:

- TOON's `normalize` returns `null` for unknown types and logs `Unsupported type FetchResponse, converting to null`.
- JSON's `default=str` falls back to the model's `__str__` / repr, producing the model's text form quoted as a single string.

MCP path uses FastMCP, which dumps pydantic itself before serialization, so this only affects the CLI.

The fix needs to live at the formatter boundary because (a) `_invoke_tool_in_process` is one of several call sites — anything that calls `format_response` is affected, and (b) the formatter is the seam where typed Python values become wire bytes. Fixing it elsewhere (e.g., in `_invoke_tool_in_process`) leaves duplicate paths.

## Goals / Non-Goals

**Goals:**
- Pydantic `BaseModel` returns render correctly via JSON and TOON in the CLI path.
- Lists / dicts containing `BaseModel`s render correctly (nested case from realistic tool returns).
- Auto-format selection (`toon_or_json`) sees the normalized payload, so a model with list/dict fields picks TOON as expected.
- Behavior for non-pydantic returns is unchanged (byte-identical).

**Non-Goals:**
- Markdown / TOON-flavored renderer for human-friendly CLI output (planned later for a2web; this change just keeps the wire format honest).
- Fixing the introspection surface (`App.cli_extras()` method vs iterable, untyped `App.tools()` results) — captured in proposal as a follow-up.
- Touching the MCP path; it already works.

## Decisions

### Decision 1: Normalize at the formatter boundary, not at the runtime call site

Pydantic-awareness is added inside `format_response` (a new `_normalize_for_encoding(value)` helper called before both `_encode_json` and `encode_toon`).

Rationale: the formatter is the single seam where Python objects become wire bytes; any current or future caller benefits. Fixing it in `_invoke_tool_in_process` would leak the concern into runtime and miss other entry points.

Alternatives considered:
- **Dump in `_invoke_tool_in_process`**: rejected — duplicates the concern across call sites, and the bug is reproducible from any code path that hands a `BaseModel` to `format_response`.
- **Fix inside `toon_format.normalize` and `_encode_json` separately**: rejected — two implementations to keep in sync; cross-format invariant (auto-selection sees the same shape) becomes harder to express.

### Decision 2: Use `model_dump(mode="json")` for normalization

Convert each `BaseModel` to a plain dict with `mode="json"` so datetimes, enums, UUIDs, etc. render as wire-friendly primitives that both encoders already handle.

Rationale: matches what FastMCP/MCP path produces, so CLI and MCP outputs stay consistent for the same tool. `mode="python"` would leave `datetime` objects in the dict and re-trigger the same problem under TOON.

Alternative: `model_dump_json()` then re-parse — rejected, redundant round-trip.

### Decision 3: Recurse through lists, tuples, and dicts

`_normalize_for_encoding` walks lists/tuples/dicts and rewrites any `BaseModel` it finds. Other values pass through unchanged.

Rationale: realistic tool returns include `list[Task]`, `dict[str, Task]`, and shapes like `{"items": [Task, Task], "next_cursor": "..."}`. Touching only top-level models would leave the most common case broken.

Stop conditions: don't recurse into arbitrary objects (only the standard container types); don't recurse into strings/bytes (they're iterable but not containers in this sense).

### Decision 4: Run `toon_or_json` auto-selection against the normalized payload

After normalization, `toon_or_json(normalized)` chooses the format. This is a behavior change only for inputs that contained `BaseModel` (which previously would have hit the "not a dict" branch and picked JSON).

Rationale: a `Task` model with list/dict fields should pick TOON, matching what a hand-written equivalent dict already does today.

## Risks / Trade-offs

- **Risk**: Normalizing recursively could be expensive for very large payloads.
  → Mitigation: the work is `O(n)` over container size and pydantic's `model_dump` is the same cost FastMCP already pays on the MCP path. No caching needed; if a tool returns enormous payloads, the encoder cost dominates anyway.

- **Risk**: A `BaseModel` subclass that overrides `model_dump` to do something unusual could now leak side effects via the CLI path.
  → Mitigation: same risk already applies on the MCP path; consistent behavior across paths is desirable. Documented in the spec scenario list.

- **Risk**: Auto-format choice flips for inputs that previously rendered as quoted-repr JSON. Anyone who depended on that broken output (unlikely — it was unusable) sees a different format.
  → Mitigation: noted in the proposal; the prior output was a bug, not a contract.

- **Trade-off**: We don't normalize arbitrary objects with a `__dict__` or dataclasses. If users want dataclass returns to work, that's a follow-up — out of scope here. Pydantic is the documented contract.
