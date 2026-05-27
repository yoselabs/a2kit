"""Mirror tests for a2kit._ldd_wire — canonical LDD wire-format primitives.

End-to-end byte-parity across emission paths is covered in
tests/packages/context/test_format_parity.py; this file holds the
direct unit behavior.
"""

from __future__ import annotations

from a2kit._ldd_wire import TEXT_CAP, _cap_text, _format_kv, format_ldd_line


def test_text_cap_default_is_60():
    assert TEXT_CAP == 60


def test_cap_text_passes_through_short():
    assert _cap_text("hi") == "hi"


def test_cap_text_truncates_long_with_ellipsis():
    long = "x" * 80
    capped = _cap_text(long)
    assert len(capped) == TEXT_CAP
    assert capped.endswith("…")


def test_format_kv_empty():
    assert _format_kv({}) == ""


def test_format_kv_string_value_uses_repr():
    assert _format_kv({"k": "v"}) == "k='v'"


def test_format_kv_non_string_value_bare():
    assert _format_kv({"n": 42}) == "n=42"


def test_format_ldd_line_shape():
    line = format_ldd_line("INFO", "hello", {"k": "v"}, 1234)
    assert line == "[ + 1.234 INFO    ] hello k='v'"


def test_format_ldd_line_empty_msg_and_fields():
    line = format_ldd_line("DEBUG", "", {}, 0)
    assert line == "[ + 0.000 DEBUG   ]"
