"""Mirror unit tests for ``a2kit.packages.log.app_log``."""

from __future__ import annotations

import logging

from a2kit.packages.log.app_log import _AppLog


def test_add_and_remove_handler_round_trips() -> None:
    app_log = _AppLog()
    handler = logging.NullHandler()
    before = len(app_log.handlers)
    app_log.add_handler(handler)
    assert handler in app_log.handlers
    assert len(app_log.handlers) == before + 1
    app_log.remove_handler(handler)
    assert handler not in app_log.handlers
    assert len(app_log.handlers) == before


def test_handlers_is_an_immutable_snapshot() -> None:
    app_log = _AppLog()
    snapshot = app_log.handlers
    assert isinstance(snapshot, tuple)
