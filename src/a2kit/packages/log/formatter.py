"""The condensed, byte-stable LLM-facing line, as a stdlib ``logging.Formatter``.

The line shape itself lives in the foundational ``a2kit._log_wire`` module (so
the CLI stderr stub and this formatter share one definition without a layer
cycle). This module wraps it as a ``logging.Formatter``. Condensing is a
property of the LLM-facing handlers (stderr, wire) only — the call-log file
deliberately does NOT condense (it keeps full fidelity).
"""

from __future__ import annotations

import logging

from a2kit._log_wire import _LEVEL_LABEL, TEXT_CAP, _cap_text, format_condensed_line

# ``_cap_text`` is re-exported (emission caps the wire message through here).
__all__ = ["TEXT_CAP", "CondensedFormatter", "_cap_text", "format_condensed_line"]


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
