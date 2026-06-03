"""Mirror unit tests for the foundational ``a2kit._log_wire`` line primitives."""

from __future__ import annotations

from a2kit._log_wire import _cap_text, _format_kv, format_condensed_line


def test_format_condensed_line_shape() -> None:
    out = format_condensed_line("INFO", "cache warm", {"host": "x.com"}, 1234)
    assert out == "[ + 1.234 INFO    ] cache warm host='x.com'"


def test_cap_text_truncates_with_ellipsis() -> None:
    capped = _cap_text("z" * 100, cap=10)
    assert len(capped) == 10
    assert capped.endswith("…")


def test_format_kv_quotes_strings_only() -> None:
    assert _format_kv({"n": 1, "s": "x"}) == "n=1 s='x'"


def test_empty_message_omits_body() -> None:
    assert format_condensed_line("DEBUG", "", {}, 0) == "[ + 0.000 DEBUG   ]"
