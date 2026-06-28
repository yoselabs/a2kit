"""Capability: per-call context (call_id, tool_name, elapsed_ms) is injected
onto every emitted record by a stdlib ``logging.Filter`` reading the
request-scope ``_CallScope`` — not threaded through the call signature.
"""

from __future__ import annotations

import logging
from typing import cast

import pytest

from a2kit.log import info
from a2kit.packages.log.scope import _CallScopeFilter, bind_call_scope
from a2kit.packages.testing.null_context import null_context

from tests._typed_records import A2kitLogRecord


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
    flt = _CallScopeFilter()
    prev = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.addFilter(flt)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.removeFilter(flt)
        logger.setLevel(prev)


async def test_record_carries_call_id_tool_elapsed_from_scope(cap: _Capture) -> None:
    with bind_call_scope(ctx=null_context(), call_id="abc123", tool_name="ask"):
        await info("fetching", host="x.com")
    assert len(cap.records) == 1
    rec = cast("A2kitLogRecord", cap.records[0])
    assert rec.call_id == "abc123"
    assert rec.tool_name == "ask"
    assert isinstance(rec.elapsed_ms, int)
    assert rec.elapsed_ms >= 0


async def test_record_outside_scope_has_null_call_id(cap: _Capture) -> None:
    await info("orphan")
    rec = cast("A2kitLogRecord", cap.records[0])
    assert rec.call_id is None
    assert rec.tool_name is None
