"""Pydantic BaseModel rendering through ``format_response``.

The CLI path used to leave BaseModel inputs un-normalized — TOON encoded them as
``null`` (with an ``Unsupported type`` warning), and JSON ``default=str``
produced the model's repr quoted as a single string. The fix is to normalize
``BaseModel`` (and BaseModels nested in lists/dicts) via
``model_dump(mode="json")`` at the formatter boundary, before either encoder
runs. These tests pin that contract.
"""

from __future__ import annotations

import json
import logging

import toon_format
from pydantic import BaseModel

from a2kit.packages.formatter import format_response, toon_or_json


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
        # explicit byte-equality against the canonical compact encoding
        expected = json.dumps(
            raw.model_dump(mode="json"),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert got.data == expected

    def test_toon_dumps_via_model_dump_no_warning(self, caplog):
        raw = Task(id="t1", title="x")
        with caplog.at_level(logging.WARNING):
            got = format_response(raw, format_hint="toon")
        assert got.format == "toon"
        assert got.data == toon_format.encode(raw.model_dump(mode="json"))
        # No "Unsupported type" log records
        assert not any("Unsupported type" in r.message for r in caplog.records)


class TestListOfBaseModels:
    def test_json(self):
        raw = [Task(id="a", title="x"), Task(id="b", title="y")]
        got = format_response(raw, format_hint="json")
        assert got.format == "json"
        assert json.loads(got.data) == [r.model_dump(mode="json") for r in raw]

    def test_toon(self):
        raw = [Task(id="a", title="x"), Task(id="b", title="y")]
        got = format_response(raw, format_hint="toon")
        assert got.format == "toon"
        assert got.data == toon_format.encode([r.model_dump(mode="json") for r in raw])


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


class TestAutoFormatSelection:
    def test_auto_picks_toon_for_model_with_list_field(self):
        raw = Project(name="P", tasks=[Task(id="a", title="x")])
        got = format_response(raw, format_hint="auto")
        assert got.format == "toon"
        assert got.data == toon_format.encode(raw.model_dump(mode="json"))

    def test_auto_picks_json_for_flat_model(self):
        raw = Task(id="a", title="x")
        got = format_response(raw, format_hint="auto")
        assert got.format == "json"


class TestNonPydanticInputsUnchanged:
    """Regression guard: normalization must not touch non-BaseModel values."""

    def test_flat_dict_json_byte_identical(self):
        raw = {"a": 1, "b": "x", "c": True, "d": None}
        got = format_response(raw, format_hint="json")
        assert got.data == json.dumps(raw, separators=(",", ":"), ensure_ascii=False)

    def test_nested_dict_toon_byte_identical(self):
        raw = {"items": [1, 2, 3], "meta": {"k": "v"}}
        got = format_response(raw, format_hint="toon")
        assert got.data == toon_format.encode(raw)

    def test_scalar_json(self):
        got = format_response("hello", format_hint="json")
        assert got.data == '"hello"'

    def test_toon_or_json_unchanged_for_non_pydantic(self):
        # Heuristic still works on plain dicts/lists.
        assert toon_or_json([{"a": 1}, {"a": 2}]) == "toon"
        assert toon_or_json({"a": 1}) == "json"
