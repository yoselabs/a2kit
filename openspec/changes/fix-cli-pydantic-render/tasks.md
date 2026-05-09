## 1. Failing tests (BDD-first)

- [x] 1.1 Add `tests/packages/formatter/test_basemodel_render.py` with fixtures: a flat `Task` model, a nested `Project(tasks=list[Task])` model.
- [x] 1.2 Test: top-level BaseModel via `format_hint="json"` returns compact JSON of `model_dump(mode="json")`.
- [x] 1.3 Test: top-level BaseModel via `format_hint="toon"` returns `encode_toon(model_dump(mode="json"))` and emits no `Unsupported type` warning (capture logging).
- [x] 1.4 Test: list of BaseModels (`[Task, Task]`) renders correctly via JSON and TOON.
- [x] 1.5 Test: dict containing BaseModel values (`{"items": [Task], "next_cursor": None}`) renders correctly via JSON.
- [x] 1.6 Test: nested BaseModel (`Project(tasks=[Task])`) dumps recursively.
- [x] 1.7 Test: auto picks TOON for `Project(tasks=[...])` and JSON for flat `Task`.
- [x] 1.8 Test: byte-identical output for non-pydantic inputs (regression guard against `_normalize_for_encoding` touching non-models).
- [x] 1.9 Run the suite — confirm all new tests fail for the expected reasons (null in TOON, quoted repr in JSON).

## 2. Implementation

- [x] 2.1 In `src/a2kit/packages/formatter/__init__.py`, add `_normalize_for_encoding(value)` that: returns `value.model_dump(mode="json")` for `BaseModel`; recurses into `list`/`tuple`/`dict`; returns other values unchanged.
- [x] 2.2 Wire `_normalize_for_encoding` into `format_response` so JSON, TOON, and `auto` paths all encode the normalized payload (and `toon_or_json` sees the normalized payload).
- [x] 2.3 Import `pydantic.BaseModel` at module top with the lightest available import path; ensure no circular import with the rest of the formatter package.
- [x] 2.4 Re-run the test suite — all new tests pass; existing formatter tests stay green.

## 3. Verification

- [x] 3.1 Reproduce the original a2web symptom locally: build a tiny app with a tool returning a `BaseModel`, run via CLI in JSON and TOON modes, confirm output matches MCP wire format expectations.
- [x] 3.2 Run `uv run pytest` (full suite) and `uv run ruff check` / `uv run mypy` (or whatever the repo uses) — clean.
- [x] 3.3 `openspec validate fix-cli-pydantic-render` — passes.

## 4. Wrap-up

- [x] 4.1 Update CHANGELOG / release notes entry under the v0.22+ line: "fix: CLI formatter renders pydantic BaseModel returns (JSON + TOON)".
- [x] 4.2 Commit on a feature branch and merge to main per project convention (no PR).
- [x] 4.3 Archive the change with `openspec archive fix-cli-pydantic-render` once merged.
