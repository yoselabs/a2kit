"""Canonical LDD wire-format primitives — the foundational, layer-exempt home.

Both ``packages/ldd/wire.py`` and ``packages/context/stderr.py`` route
through here so the ``[ +s.mmm LEVEL] msg key=val`` line shape is
defined exactly once and byte-equality across emission paths is a
language-level guarantee, not a sync-by-test invariant.

This module is intentionally a top-level ``a2kit.*`` foundational
module (see ``packages/lint/layers.py::FOUNDATIONAL_CORE_MODULES``):
both ``packages/ldd/`` (the canonical emitter) and ``packages/context/``
(the stderr-only stub for environments without an LDD pipeline) are at
layer L0, so neither can import from the other without a cycle —
``ldd.ambient`` already imports from ``context.request_scope``
under ``# noqa: A2K-LAYER`` (cycle-adjacent today). A new direct
``context → ldd`` import would close the cycle outright. Putting the
shared primitives one level below the L0 layer resolves the constraint
cleanly.

Stdlib-only. No a2kit imports.
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

    ``msg`` is capped at :data:`TEXT_CAP` chars; ``fields`` are formatted
    via Python ``repr`` for strings (preserving quotes) and bare-printed
    for everything else.
    """
    elapsed_s = elapsed_ms / 1000.0
    msg_capped = _cap_text(msg)
    head = f"[ +{elapsed_s:6.3f} {level:<8}]"
    body = f" {msg_capped}" if msg_capped else ""
    kv = _format_kv(fields)
    tail = f" {kv}" if kv else ""
    return head + body + tail


__all__ = ["TEXT_CAP", "_cap_text", "_format_kv", "format_ldd_line"]
