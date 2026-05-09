## Why

a2kit tools are encouraged to return typed pydantic `BaseModel`s (the README, MCP path, and tracker example all assume it), but the CLI path silently degrades them: TOON encoding logs `Unsupported type … converting to null`, and JSON falls back to `json.dumps(default=str)` which str()'s the model. MCP via FastMCP works because FastMCP knows pydantic; the CLI doesn't. Surfaced building a2web PR1 with a stub tool returning a `FetchResponse` model — reproducible with the upstream tracker example. Users who follow the typed-return guidance get unusable CLI output.

## What Changes

- `format_response` (src/a2kit/packages/formatter/__init__.py) normalizes pydantic `BaseModel` inputs via `.model_dump(mode="json")` before encoding for both JSON and TOON paths.
- Lists/dicts containing `BaseModel` instances are recursively normalized at the same boundary so nested models render the same way.
- `toon_or_json` auto-selection runs against the normalized payload, not the raw model, so a model with list/dict fields correctly picks TOON.
- Add unit tests covering: top-level BaseModel, list of BaseModels, dict with BaseModel values, nested BaseModel, JSON path, TOON path, auto path.

## Capabilities

### New Capabilities
- `cli-response-encoding`: Defines how `format_response` normalizes tool return values (including pydantic `BaseModel`) before TOON/JSON encoding, and how the auto-format selection runs against the normalized payload.

### Modified Capabilities
<!-- None — no existing capability covers formatter behavior. -->

## Impact

- Code: `src/a2kit/packages/formatter/__init__.py` (normalization helper + `format_response`); `src/a2kit/packages/cli/runtime.py` unchanged (boundary stays in formatter).
- Tests: new `tests/packages/formatter/test_basemodel_render.py` (or extends existing formatter tests).
- Users: typed CLI output becomes correct; no behavioral change for non-pydantic returns. No public API change.
- Dependencies: pydantic is already a transitive runtime dep via FastMCP / app surface — no new dep.
- Adjacent (out of scope, captured for follow-up): `App.cli_extras()` is a method (not iterable) and `App.tools()` returns bound methods rather than typed descriptors — inconsistent introspection surface for tests. Not addressed here.
