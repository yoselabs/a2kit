"""LDD wire formatting — the canonical ``[ +s.mmm LEVEL] msg key=val`` line.

Shared by the CLI stub (``StderrToolContext._emit``) and any transport that
wants byte-identical rendering. The ``msg`` portion is capped at
:data:`TEXT_CAP` chars with ``…`` elision. No a2kit dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Maximum characters for the ``msg`` portion of an LDD line / log payload.
TEXT_CAP: int = 60


def _cap_text(text: str, cap: int = TEXT_CAP) -> str:
    """Truncate ``text`` to ``cap`` characters, replacing the last with ``…``."""
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _format_kv(fields: Mapping[str, Any]) -> str:
    if not fields:
        return ""
    return " ".join(f"{k}={v!r}" if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())


def format_ldd_line(level: str, msg: str, fields: Mapping[str, Any], elapsed_ms: int) -> str:
    """Build the canonical LDD line: ``[ +s.mmm LEVEL] <msg-capped> key=val ...``.

    Used by both the CLI stub (``StderrToolContext._emit``) and any future
    transport that wants byte-identical rendering. ``msg`` is capped at
    :data:`TEXT_CAP` chars; ``fields`` are formatted via Python ``repr`` for
    strings (preserving quotes) and bare-printed for everything else.
    """
    elapsed_s = elapsed_ms / 1000.0
    msg_capped = _cap_text(msg)
    head = f"[ +{elapsed_s:6.3f} {level:<8}]"
    body = f" {msg_capped}" if msg_capped else ""
    kv = _format_kv(fields)
    tail = f" {kv}" if kv else ""
    return head + body + tail
