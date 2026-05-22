"""Tests for `a2kit.packages.ldd.wire` — the canonical LDD line format."""

from __future__ import annotations

from a2kit.packages.ldd.wire import TEXT_CAP, format_ldd_line


def test_format_ldd_line_shape() -> None:
    """A line carries the elapsed head, the message, and repr-formatted fields."""
    line = format_ldd_line("INFO", "hello", {"key": "val", "n": 3}, elapsed_ms=1234)
    assert line.startswith("[ +")
    assert "INFO" in line
    assert "hello" in line
    assert "key='val'" in line  # str field uses repr (keeps quotes)
    assert "n=3" in line  # non-str field is bare-printed


def test_format_ldd_line_elapsed_basis() -> None:
    """``elapsed_ms`` renders as seconds with three decimals."""
    assert "+ 1.234" in format_ldd_line("INFO", "x", {}, elapsed_ms=1234)


def test_format_ldd_line_empty_message_and_fields() -> None:
    """An empty message and no fields collapse to just the head."""
    assert format_ldd_line("DEBUG", "", {}, elapsed_ms=0).strip().endswith("]")


def test_format_ldd_line_caps_message_at_text_cap() -> None:
    """A message longer than ``TEXT_CAP`` is elided with ``…``."""
    long_msg = "x" * (TEXT_CAP + 50)
    line = format_ldd_line("INFO", long_msg, {}, elapsed_ms=0)
    assert "…" in line
    assert "x" * (TEXT_CAP + 50) not in line
