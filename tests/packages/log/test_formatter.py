"""Mirror unit tests for ``a2kit.packages.log.formatter`` — the condensed,
byte-stable LLM-facing line ``[ +s.mmm LEVEL] msg key=val``.
"""

from __future__ import annotations

import logging

from a2kit.packages.log.formatter import CondensedFormatter


def _record(levelno: int, msg: str, fields: dict | None = None, elapsed_ms: int = 1234) -> logging.LogRecord:
    rec = logging.LogRecord("a2kit", levelno, __file__, 0, msg, None, None)
    rec.a2kit_fields = fields or {}
    rec.elapsed_ms = elapsed_ms
    return rec


def test_info_line_shape() -> None:
    out = CondensedFormatter().format(_record(logging.INFO, "cache warm", {"host": "x.com"}))
    assert out == "[ + 1.234 INFO    ] cache warm host='x.com'"


def test_warning_label_is_warn() -> None:
    out = CondensedFormatter().format(_record(logging.WARNING, "stale", {}, elapsed_ms=0))
    assert out == "[ + 0.000 WARN    ] stale"


def test_long_message_is_capped() -> None:
    out = CondensedFormatter().format(_record(logging.INFO, "z" * 100, {}, elapsed_ms=0))
    # 60-char cap with a trailing ellipsis.
    body = out.split("] ", 1)[1]
    assert len(body) == 60
    assert body.endswith("…")


def test_missing_elapsed_defaults_to_zero() -> None:
    rec = logging.LogRecord("a2kit", logging.ERROR, __file__, 0, "boom", None, None)
    out = CondensedFormatter().format(rec)
    assert out == "[ + 0.000 ERROR   ] boom"
