"""Canonical condensed-line primitives — the foundational, layer-exempt home.

Both ``packages/log/formatter.py`` (the ``CondensedFormatter``) and
``packages/context/stderr.py`` (the CLI stderr stub) route through here so the
``[ +s.mmm LEVEL] msg key=val`` line shape is defined exactly once and
byte-equality across emission paths is a language-level guarantee.

This is intentionally a top-level ``a2kit.*`` foundational module (see
``packages/lint/layers.py::FOUNDATIONAL_CORE_MODULES``): ``packages/log/`` and
``packages/context/`` both sit at L0, so neither can import the other without a
cycle — ``log.scope`` already imports ``context.request_scope`` (lazily).
Putting the shared line primitives one level below L0 resolves that cleanly.

Stdlib-only. No a2kit imports.
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


__all__ = ["TEXT_CAP", "_cap_text", "_format_kv", "format_condensed_line"]
