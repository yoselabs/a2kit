"""The condensed, byte-stable LLM-facing line, as a stdlib ``logging.Formatter``.

Folds the former ``wire.py`` / ``_ldd_wire`` line shape into a Formatter:
``[ +s.mmm LEVEL] <msg-capped> key=val ...``. Condensing is a property of the
LLM-facing handlers (stderr, wire) only — the call-log file deliberately does
NOT condense (it keeps full fidelity). Stdlib-only; no a2kit imports.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Maximum characters for the ``msg`` portion of a condensed line.
TEXT_CAP: int = 60

#: Map stdlib level numbers to the terse a2kit labels (WARNING -> WARN).
_LEVEL_LABEL: dict[int, str] = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "ERROR",
}


def _cap_text(text: str, cap: int = TEXT_CAP) -> str:
    """Truncate ``text`` to ``cap`` chars, replacing the last with ``…``."""
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _format_kv(fields: Mapping[str, Any]) -> str:
    if not fields:
        return ""
    return " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())


def format_condensed_line(level: str, msg: str, fields: Mapping[str, Any], elapsed_ms: int) -> str:
    """Build ``[ +s.mmm LEVEL] <msg-capped> key=val ...`` (byte-stable)."""
    elapsed_s = elapsed_ms / 1000.0
    msg_capped = _cap_text(msg)
    head = f"[ +{elapsed_s:6.3f} {level:<8}]"
    body = f" {msg_capped}" if msg_capped else ""
    kv = _format_kv(fields)
    tail = f" {kv}" if kv else ""
    return head + body + tail


class CondensedFormatter(logging.Formatter):
    """Render an ``a2kit`` record to the condensed line.

    Reads the structured ``a2kit_fields`` payload and the filter-injected
    ``elapsed_ms`` off the record; falls back to ``0`` when no scope is active.
    """

    def format(self, record: logging.LogRecord) -> str:
        level = _LEVEL_LABEL.get(record.levelno, record.levelname)
        fields = getattr(record, "a2kit_fields", {}) or {}
        elapsed_ms = getattr(record, "elapsed_ms", None) or 0
        return format_condensed_line(level, record.getMessage(), fields, elapsed_ms)


__all__ = ["TEXT_CAP", "CondensedFormatter", "format_condensed_line"]
