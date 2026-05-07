"""Tests for a2kit.formatter — TOON/JSON heuristic + recursive truncation."""

from __future__ import annotations

import json

from a2kit import formatter


def test_truncate_short_string_unchanged() -> None:
    assert formatter.truncate("hi", max_chars=100) == "hi"


def test_truncate_long_string() -> None:
    out = formatter.truncate("x" * 100, max_chars=10, marker="…")
    assert out == "x" * 10 + "…"


def test_truncate_dict_recursive() -> None:
    out = formatter.truncate({"a": "x" * 100, "b": 1}, max_chars=5, marker="…")
    assert out == {"a": "xxxxx…", "b": 1}


def test_truncate_list_and_tuple_returns_list() -> None:
    out = formatter.truncate(("a", "x" * 100), max_chars=5, marker="…")
    assert out == ["a", "xxxxx…"]


def test_truncate_passthrough_for_non_string() -> None:
    assert formatter.truncate(42) == 42
    assert formatter.truncate(None) is None


def test_toon_uniform_rows() -> None:
    fmt, payload = formatter.toon_or_json([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    assert fmt == "tsv"
    assert payload == "a\tb\n1\t2\n3\t4"


def test_toon_handles_none_values() -> None:
    fmt, payload = formatter.toon_or_json([{"a": None, "b": 2}])
    assert fmt == "tsv"
    assert payload == "a\tb\n\t2"


def test_json_for_single_dict() -> None:
    fmt, payload = formatter.toon_or_json({"a": 1})
    assert fmt == "json"
    assert json.loads(payload) == {"a": 1}


def test_json_for_empty_list() -> None:
    fmt, payload = formatter.toon_or_json([])
    assert fmt == "json"
    assert payload == "[]"


def test_json_for_heterogeneous_list() -> None:
    fmt, payload = formatter.toon_or_json([{"a": 1}, {"b": 2}])
    assert fmt == "json"
    assert json.loads(payload) == [{"a": 1}, {"b": 2}]


def test_json_for_list_of_non_dicts() -> None:
    fmt, payload = formatter.toon_or_json([1, 2, 3])
    assert fmt == "json"
    assert json.loads(payload) == [1, 2, 3]


def test_toon_for_nested_values() -> None:
    """List of dicts with at least one nested value → toon (JSON-encoded cells)."""
    fmt, payload = formatter.toon_or_json([{"a": 1, "tags": ["x", "y"]}, {"a": 2, "tags": []}])
    assert fmt == "toon"
    assert '["x","y"]' in payload  # nested list as compact JSON
    assert "[]" in payload


def test_toon_nested_dict_value_json_encoded() -> None:
    fmt, payload = formatter.toon_or_json([{"a": 1, "meta": {"k": "v"}}])
    assert fmt == "toon"
    assert '{"k":"v"}' in payload


def test_format_response_envelope_toon() -> None:
    out = formatter.format_response([{"a": 1}, {"a": 2}])
    assert isinstance(out, formatter.Response)
    assert out.format == "tsv"
    assert out.data == "a\n1\n2"
    assert out.truncated is False
    assert out.next_cursor is None


def test_format_response_envelope_json_truncated() -> None:
    out = formatter.format_response({"big": "x" * 5000}, truncate_at=10, marker="…[truncated]")
    assert out.format == "json"
    assert out.truncated is True
    assert "…[truncated]" in out.data


def test_format_response_default_marker_propagates() -> None:
    out = formatter.format_response("x" * 5000)
    # single string is not list-of-dicts → JSON
    assert out.format == "json"
    assert out.truncated is True
