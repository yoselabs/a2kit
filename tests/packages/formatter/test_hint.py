"""``format_response`` — the legacy ``format_hint``-vocabulary adapter."""

from __future__ import annotations

import json

from a2kit.packages.formatter import Response, format_response


class TestFormatResponseAuto:
    """Outside a tool-dispatch context, ``auto`` falls back to JSON."""

    def test_auto_for_list_of_dicts_is_json(self):
        data = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        r = format_response(data)
        assert r.format == "json"
        assert json.loads(r.data) == data

    def test_auto_for_flat_dict_is_json(self):
        data = {"a": 1, "b": 2}
        r = format_response(data)
        assert r.format == "json"
        assert json.loads(r.data) == data

    def test_auto_for_scalar_is_json(self):
        r = format_response("hi")
        assert r.format == "json"
        assert json.loads(r.data) == "hi"


class TestFormatResponseHints:
    def test_json_hint_forces_json(self):
        data = [{"a": 1}, {"a": 2}]
        r = format_response(data, format_hint="json")
        assert r.format == "json"
        assert json.loads(r.data) == data


class TestFormatResponseReturnType:
    def test_returns_response_dataclass(self):
        r = format_response({"a": 1})
        assert isinstance(r, Response)
        assert hasattr(r, "data")
        assert hasattr(r, "format")
