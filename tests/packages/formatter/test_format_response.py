"""``format_response`` orchestrator + ``toon_or_json`` heuristic + ``truncate``."""

from __future__ import annotations

import json

import toon_format

from a2kit.packages.formatter import (
    TRUNCATION_MARKER,
    Response,
    format_response,
    toon_or_json,
    truncate,
)


class TestToonOrJsonHeuristic:
    """Auto rule: structured nested data → TOON; flat / scalar → JSON."""

    # TOON cases
    def test_list_of_dicts_is_toon(self):
        assert toon_or_json([{"a": 1}, {"a": 2}]) == "toon"

    def test_dict_with_list_value_is_toon(self):
        assert toon_or_json({"items": [1, 2, 3]}) == "toon"

    def test_dict_with_dict_value_is_toon(self):
        assert toon_or_json({"meta": {"x": 1}}) == "toon"

    def test_list_of_lists_is_toon(self):
        assert toon_or_json([[1, 2], [3, 4]]) == "toon"

    # JSON cases
    def test_scalar_string_is_json(self):
        assert toon_or_json("hello") == "json"

    def test_scalar_int_is_json(self):
        assert toon_or_json(42) == "json"

    def test_none_is_json(self):
        assert toon_or_json(None) == "json"

    def test_flat_dict_is_json(self):
        assert toon_or_json({"a": 1, "b": "x"}) == "json"

    def test_flat_list_is_json(self):
        assert toon_or_json([1, 2, 3]) == "json"

    def test_empty_dict_is_json(self):
        assert toon_or_json({}) == "json"

    def test_empty_list_is_json(self):
        assert toon_or_json([]) == "json"


class TestFormatResponseAuto:
    def test_auto_picks_toon_for_list_of_dicts(self):
        data = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        r = format_response(data)
        assert r.format == "toon"
        assert r.data == toon_format.encode(data)

    def test_auto_picks_json_for_flat_dict(self):
        data = {"a": 1, "b": 2}
        r = format_response(data)
        assert r.format == "json"
        assert json.loads(r.data) == data

    def test_auto_picks_json_for_scalar(self):
        r = format_response("hi")
        assert r.format == "json"
        assert json.loads(r.data) == "hi"


class TestFormatResponseHints:
    def test_toon_hint_forces_toon(self):
        # A flat dict that auto would route to JSON — toon hint overrides.
        data = {"a": 1}
        r = format_response(data, format_hint="toon")
        assert r.format == "toon"
        assert r.data == toon_format.encode(data)

    def test_json_hint_forces_json(self):
        # Nested data that auto would route to TOON — json hint overrides.
        data = [{"a": 1}, {"a": 2}]
        r = format_response(data, format_hint="json")
        assert r.format == "json"
        assert json.loads(r.data) == data

    def test_toon_byte_identical_to_library(self):
        # The contract: format_response(..., toon).data == toon_format.encode(...)
        data = {"outer": {"inner": [{"x": 1}, {"x": 2}]}}
        r = format_response(data, format_hint="toon")
        assert r.data == toon_format.encode(data)


class TestFormatResponseReturnType:
    def test_returns_response_dataclass(self):
        r = format_response({"a": 1})
        assert isinstance(r, Response)
        assert hasattr(r, "data")
        assert hasattr(r, "format")


class TestTruncate:
    def test_under_cap_passthrough(self):
        assert truncate("hello", max_chars=100) == "hello"

    def test_at_cap_passthrough(self):
        s = "a" * 50
        assert truncate(s, max_chars=50) == s

    def test_over_cap_truncated(self):
        s = "a" * 100
        result = truncate(s, max_chars=50)
        assert result == "a" * 50 + TRUNCATION_MARKER
        assert result.endswith(TRUNCATION_MARKER)

    def test_default_cap(self):
        # Default is 50_000 — payloads smaller than that pass through.
        s = "x" * 49_000
        assert truncate(s) == s

    def test_default_cap_truncates(self):
        s = "x" * 60_000
        result = truncate(s)
        assert len(result) == 50_000 + len(TRUNCATION_MARKER)
        assert result.endswith(TRUNCATION_MARKER)
