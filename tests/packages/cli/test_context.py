"""``StderrToolContext`` emits ``[ +s.mmm LEVEL] msg key=val`` lines to stderr.

Wire format: relative elapsed timestamps from context construction, formatted
as ``+s.mmm`` with three-decimal-place seconds. ``ctx.report`` validates
payload against the declared ``report_type`` even when reports are disabled.
"""

from __future__ import annotations

import asyncio
import io
import re
import sys

import pytest
from pydantic import BaseModel

from a2kit.exceptions import ReportTypeMismatch, ReportTypeNotDeclared
from a2kit.packages.cli.context import StderrToolContext


def _capture_stderr(callable_, *args, **kwargs) -> str:
    buf = io.StringIO()
    saved = sys.stderr
    sys.stderr = buf
    try:
        callable_(*args, **kwargs)
    finally:
        sys.stderr = saved
    return buf.getvalue()


_PREFIX = re.compile(r"^\[ \+\s*\d+\.\d{3} \w+\s*]")


def test_info_no_fields_emits_prefix_and_msg() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.info, "hello")
    assert _PREFIX.match(out)
    assert "INFO" in out
    assert " hello" in out


def test_warning_with_fields_emits_kv() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.warning, "stuck", retry=3, where="foo")
    assert "WARN" in out
    assert "stuck" in out
    assert "retry=3" in out
    assert "where='foo'" in out


def test_error_repr_quotes_strings_only() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.error, "boom", code=42, name="db")
    assert "code=42" in out
    assert "name='db'" in out


def test_debug_emits_debug_level() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(ctx.debug, "internal")
    assert "DEBUG" in out
    assert "internal" in out


def test_report_progress_uses_progress_level() -> None:
    ctx = StderrToolContext()

    def go() -> None:
        asyncio.run(ctx.report_progress(5, total=10))

    out = _capture_stderr(go)
    assert "progress" in out
    assert "current=5" in out
    assert "total=10" in out


def test_satisfies_toolcontext_protocol() -> None:
    from a2kit.runtime import ToolContext

    assert isinstance(StderrToolContext(), ToolContext)


# --- LDD: events --- #


def test_event_emits_named_payload() -> None:
    ctx = StderrToolContext()

    def go() -> None:
        asyncio.run(ctx.event("api.fetched", count=30, source="primary"))

    out = _capture_stderr(go)
    assert "event" in out
    assert "api.fetched" in out
    assert "count=30" in out
    assert "source='primary'" in out


def test_event_empty_payload_silent_kv() -> None:
    ctx = StderrToolContext()
    out = _capture_stderr(lambda: asyncio.run(ctx.event("phase.started")))
    assert "phase.started" in out


def test_event_disabled_emits_nothing() -> None:
    ctx = StderrToolContext(events_enabled=False)
    out = _capture_stderr(lambda: asyncio.run(ctx.event("ignored")))
    assert out == ""


# --- LDD: reports --- #


class BatchReport(BaseModel):
    batch: int
    accepted: int
    rejected: int


def test_report_happy_path() -> None:
    ctx = StderrToolContext(report_type=BatchReport, tool_name="t")
    out = _capture_stderr(lambda: asyncio.run(ctx.report(BatchReport(batch=4, accepted=12, rejected=0))))
    assert "report" in out
    assert "BatchReport" in out
    assert "batch=4" in out
    assert "accepted=12" in out


def test_report_without_declared_type_raises() -> None:
    ctx = StderrToolContext(tool_name="t")
    with pytest.raises(ReportTypeNotDeclared):
        asyncio.run(ctx.report({"any": "dict"}))


def test_report_type_mismatch_raises() -> None:
    ctx = StderrToolContext(report_type=BatchReport, tool_name="t")
    with pytest.raises(ReportTypeMismatch):
        asyncio.run(ctx.report({"not": "a model"}))


def test_report_disabled_still_validates() -> None:
    """Disabled emission STILL validates types — keeps tests deterministic."""
    ctx = StderrToolContext(report_type=BatchReport, tool_name="t", reports_enabled=False)
    # Type-correct payload: no emission, no error.
    out = _capture_stderr(lambda: asyncio.run(ctx.report(BatchReport(batch=1, accepted=1, rejected=0))))
    assert out == ""
    # Type-incorrect payload: still raises.
    with pytest.raises(ReportTypeMismatch):
        asyncio.run(ctx.report({"wrong": "shape"}))


def test_elapsed_timestamp_increments() -> None:
    """The +s.mmm prefix grows over time."""
    import time

    ctx = StderrToolContext()
    out1 = _capture_stderr(ctx.info, "first")
    time.sleep(0.05)
    out2 = _capture_stderr(ctx.info, "second")
    # Extract the elapsed value from each line and compare.
    e1 = float(out1.split("+")[1].split()[0])
    e2 = float(out2.split("+")[1].split()[0])
    assert e2 > e1
