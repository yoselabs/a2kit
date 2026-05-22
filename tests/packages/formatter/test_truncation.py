"""Tests for `a2kit.packages.formatter.truncation` — the payload-size cap."""

from __future__ import annotations

from a2kit.packages.formatter import TRUNCATION_MARKER, truncate


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
