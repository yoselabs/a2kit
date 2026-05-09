"""Pydantic BaseModel rendering through ``format_response``.

The CLI path used to leave BaseModel inputs un-normalized — the JSON
``default=str`` fallback produced the model's repr quoted as a single string.
The fix is to normalize ``BaseModel`` (and BaseModels nested in lists/dicts)
via ``model_dump(mode="json")`` at the formatter boundary, before the encoder
runs.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from a2kit.packages.formatter import format_response


class Task(BaseModel):
    id: str
    title: str


class Project(BaseModel):
    name: str
    tasks: list[Task]


class TestTopLevelBaseModel:
    def test_json_dumps_via_model_dump(self):
        raw = Task(id="t1", title="x")
        got = format_response(raw, format_hint="json")
        assert got.format == "json"
        assert json.loads(got.data) == raw.model_dump(mode="json")
        expected = json.dumps(
            raw.model_dump(mode="json"),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert got.data == expected


class TestListOfBaseModels:
    def test_json(self):
        raw = [Task(id="a", title="x"), Task(id="b", title="y")]
        got = format_response(raw, format_hint="json")
        assert got.format == "json"
        assert json.loads(got.data) == [r.model_dump(mode="json") for r in raw]


class TestDictWithBaseModelValues:
    def test_json_envelope(self):
        raw = {"items": [Task(id="a", title="x")], "next_cursor": None}
        got = format_response(raw, format_hint="json")
        assert got.format == "json"
        assert json.loads(got.data) == {
            "items": [{"id": "a", "title": "x"}],
            "next_cursor": None,
        }


class TestNestedBaseModel:
    def test_json_recurses_via_model_dump(self):
        raw = Project(name="P", tasks=[Task(id="a", title="x"), Task(id="b", title="y")])
        got = format_response(raw, format_hint="json")
        assert got.format == "json"
        assert json.loads(got.data) == raw.model_dump(mode="json")


class TestAutoFallback:
    """Outside a tool-dispatch context, ``auto`` falls back to JSON."""

    def test_auto_for_flat_model_is_json(self):
        raw = Task(id="a", title="x")
        got = format_response(raw, format_hint="auto")
        assert got.format == "json"

    def test_auto_for_nested_model_is_json(self):
        # Type-driven routing happens at the descriptor level (CLI runtime),
        # not in `format_response("auto")` directly. Direct callers get JSON.
        raw = Project(name="P", tasks=[Task(id="a", title="x")])
        got = format_response(raw, format_hint="auto")
        assert got.format == "json"


class TestNonPydanticInputsUnchanged:
    """Regression guard: normalization must not touch non-BaseModel values."""

    def test_flat_dict_json_byte_identical(self):
        raw = {"a": 1, "b": "x", "c": True, "d": None}
        got = format_response(raw, format_hint="json")
        assert got.data == json.dumps(raw, separators=(",", ":"), ensure_ascii=False)

    def test_scalar_json(self):
        got = format_response("hello", format_hint="json")
        assert got.data == '"hello"'


class TestToonRemoved:
    def test_format_hint_toon_raises(self):
        import pytest

        with pytest.raises(ValueError, match="toon"):
            format_response({"a": 1}, format_hint="toon")  # type: ignore[arg-type]
