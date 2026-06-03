"""Log level vocabulary, folded onto stdlib ``logging`` levels.

The five-name vocabulary (``trace`` / ``debug`` / ``info`` / ``warning`` /
``error``) maps to stdlib level numbers. ``trace`` is a custom level below
``DEBUG`` (registered once via :func:`install_trace_level`); the other four
ARE the stdlib levels. This module is pure type-vocabulary + the registration
helper — no emission behaviour lives here.
"""

from __future__ import annotations

import logging
from typing import Literal

LogLevel = Literal["trace", "debug", "info", "warning", "error"]

#: Custom numeric level for ``trace`` (below stdlib DEBUG=10).
TRACE_LEVEL: int = 5

#: Map the vocabulary to stdlib level numbers.
LOG_LEVEL_NUMBER: dict[LogLevel, int] = {
    "trace": TRACE_LEVEL,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def install_trace_level() -> None:
    """Register the ``TRACE`` level name with stdlib ``logging`` (idempotent)."""
    if logging.getLevelName(TRACE_LEVEL) != "TRACE":
        logging.addLevelName(TRACE_LEVEL, "TRACE")


__all__ = ["LOG_LEVEL_NUMBER", "TRACE_LEVEL", "LogLevel", "install_trace_level"]
