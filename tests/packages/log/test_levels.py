"""Mirror unit tests for ``a2kit.packages.log.levels``."""

from __future__ import annotations

import logging

from a2kit.packages.log.levels import LOG_LEVEL_NUMBER, TRACE_LEVEL, install_trace_level


def test_vocabulary_maps_to_stdlib_levels() -> None:
    assert LOG_LEVEL_NUMBER["debug"] == logging.DEBUG
    assert LOG_LEVEL_NUMBER["info"] == logging.INFO
    assert LOG_LEVEL_NUMBER["warning"] == logging.WARNING
    assert LOG_LEVEL_NUMBER["error"] == logging.ERROR


def test_trace_is_below_debug() -> None:
    assert LOG_LEVEL_NUMBER["trace"] == TRACE_LEVEL
    assert TRACE_LEVEL < logging.DEBUG


def test_install_trace_level_is_idempotent() -> None:
    install_trace_level()
    install_trace_level()
    assert logging.getLevelName(TRACE_LEVEL) == "TRACE"
