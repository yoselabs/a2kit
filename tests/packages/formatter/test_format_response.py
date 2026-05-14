"""``format_response`` orchestrator + ``truncate`` (post-TOON).

TOON-specific tests moved out — TOON was removed from the wire-format menu.
TSV and page-tsv have their own dedicated test files.
"""

from __future__ import annotations

import json

import pytest

from a2kit.packages.formatter import (
    TRUNCATION_MARKER,
    Response,
    format_response,
    truncate,
)


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

    def test_toon_hint_raises(self):
        with pytest.raises(ValueError, match="toon"):
            format_response({"a": 1}, format_hint="toon")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument


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
        s = "x" * 49_000
        assert truncate(s) == s

    def test_default_cap_truncates(self):
        s = "x" * 60_000
        result = truncate(s)
        assert len(result) == 50_000 + len(TRUNCATION_MARKER)
        assert result.endswith(TRUNCATION_MARKER)
