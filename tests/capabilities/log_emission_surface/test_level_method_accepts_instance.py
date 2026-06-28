"""Capability: a level method accepts a typed instance as the structured payload.

The ``event()`` verb is gone, but the typed-instance ergonomic survives under
the level methods (a2web's 28-site idiom). ``info(instance)`` dumps the
instance to a JSON-safe dict (enum values unwrapped) carried on the record's
``a2kit_fields``; the message defaults to the type name. Extra kwargs merge in
after the instance fields.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import cast

import pytest

from a2kit.log import info

from tests._typed_records import A2kitLogRecord


class _Verdict(Enum):
    OK = "ok"
    FAIL = "fail"


@dataclass
class _TierEnded:
    step: str
    dur_ms: int
    verdict: _Verdict


class _Capture(logging.Handler):
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
    prev = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)


async def test_instance_becomes_dumped_payload_enum_unwrapped(cap: _Capture) -> None:
    await info(_TierEnded(step="extract", dur_ms=300, verdict=_Verdict.OK))
    assert len(cap.records) == 1
    rec = cast("A2kitLogRecord", cap.records[0])
    assert rec.levelno == logging.INFO
    assert rec.getMessage() == "_TierEnded"
    assert rec.a2kit_fields == {"step": "extract", "dur_ms": 300, "verdict": "ok"}


async def test_extra_kwargs_merge_after_instance_fields(cap: _Capture) -> None:
    await info(_TierEnded(step="x", dur_ms=1, verdict=_Verdict.FAIL), note="late")
    rec = cast("A2kitLogRecord", cap.records[0])
    assert rec.a2kit_fields == {"step": "x", "dur_ms": 1, "verdict": "fail", "note": "late"}
