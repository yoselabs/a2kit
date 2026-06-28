"""Capability: the refounded ``a2kit.log`` level methods route through stdlib logging.

The four level methods (``debug``/``info``/``warning``/``error``) are the sole
emission surface. Each emits ONE stdlib ``LogRecord`` on the ``a2kit`` logger at
the matching severity, carrying user fields under a structured ``a2kit_fields``
attribute (avoids reserved ``LogRecord`` attribute collisions).
"""

from __future__ import annotations

import logging
from typing import cast

import pytest

from a2kit.log import debug, error, info, warning

from tests._typed_records import A2kitLogRecord


class _Capture(logging.Handler):
    """Collect every record the ``a2kit`` logger emits."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def cap() -> object:
    logger = logging.getLogger("a2kit")
    handler = _Capture()
    handler.setLevel(logging.DEBUG)
    prev_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


async def test_info_routes_at_info_with_fields(cap: _Capture) -> None:
    await info("cache warm", host="x.com")
    assert len(cap.records) == 1
    rec = cast("A2kitLogRecord", cap.records[0])
    assert rec.levelno == logging.INFO
    assert rec.getMessage() == "cache warm"
    assert rec.a2kit_fields == {"host": "x.com"}


async def test_warning_routes_at_warning(cap: _Capture) -> None:
    await warning("cookies stale", host="x.com")
    assert len(cap.records) == 1
    assert cap.records[0].levelno == logging.WARNING
    assert cast("A2kitLogRecord", cap.records[0]).a2kit_fields == {"host": "x.com"}


async def test_error_routes_at_error(cap: _Capture) -> None:
    await error("boom")
    assert len(cap.records) == 1
    assert cap.records[0].levelno == logging.ERROR


async def test_debug_routes_at_debug(cap: _Capture) -> None:
    await debug("html", size=1024)
    assert len(cap.records) == 1
    assert cap.records[0].levelno == logging.DEBUG
    assert cast("A2kitLogRecord", cap.records[0]).a2kit_fields == {"size": 1024}
