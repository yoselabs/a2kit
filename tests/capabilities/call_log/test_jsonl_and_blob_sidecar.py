"""Capability: the call-log file handler writes one JSON object per line,
content-addresses large bodies to ``bodies/<hash>`` sidecars, and keeps every
record on one physical line (newlines JSON-escaped).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from a2kit.packages.log.call_log import CallLogFileHandler, CallRecord


def _emit(handler: CallLogFileHandler, record: CallRecord) -> None:
    log_record = logging.LogRecord("a2kit.calls", logging.INFO, __file__, 0, "", None, None)
    log_record.a2kit_call_record = record  # type: ignore[attr-defined]
    handler.emit(log_record)


def _rows(log_dir: Path) -> list[str]:
    files = sorted((log_dir / "calls").glob("*.jsonl"))
    return [line for f in files for line in f.read_text().splitlines()]


def test_large_body_is_content_addressed_not_inlined(tmp_path: Path) -> None:
    handler = CallLogFileHandler(log_dir=tmp_path, inline_threshold=16)
    big = "x" * 200
    _emit(
        handler,
        CallRecord(call_id="c1", tool="ask", domain="x.com", principal=None, elapsed_ms=5, args={"url": "https://x.com"}, result=big),
    )
    handler.close()

    lines = _rows(tmp_path)
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["call_id"] == "c1"
    assert row["domain"] == "x.com"
    assert "result" not in row
    assert "result_hash" in row
    sidecar = tmp_path / "bodies" / row["result_hash"]
    assert sidecar.read_text() == big


def test_small_value_stays_inline(tmp_path: Path) -> None:
    handler = CallLogFileHandler(log_dir=tmp_path, inline_threshold=1000)
    _emit(handler, CallRecord(call_id="c2", tool="ask", domain=None, principal=None, elapsed_ms=1, args={}, result="ok"))
    handler.close()

    row = json.loads(_rows(tmp_path)[0])
    assert row["result"] == "ok"
    assert "result_hash" not in row


def test_newline_bearing_value_stays_one_physical_line(tmp_path: Path) -> None:
    handler = CallLogFileHandler(log_dir=tmp_path, inline_threshold=1000)
    _emit(handler, CallRecord(call_id="c3", tool="ask", domain=None, principal=None, elapsed_ms=1, args={}, result="line1\nline2\nline3"))
    handler.close()

    lines = _rows(tmp_path)
    assert len(lines) == 1
    assert json.loads(lines[0])["result"] == "line1\nline2\nline3"


def test_row_carries_span_fields(tmp_path: Path) -> None:
    handler = CallLogFileHandler(log_dir=tmp_path, inline_threshold=1000)
    _emit(
        handler,
        CallRecord(
            call_id="c4",
            tool="ask",
            domain=None,
            principal="alice",
            elapsed_ms=2,
            args={},
            result=None,
            trace_id="t1",
            span_id="s1",
            parent_span_id="p1",
        ),
    )
    handler.close()

    row = json.loads(_rows(tmp_path)[0])
    assert row["trace_id"] == "t1"
    assert row["span_id"] == "s1"
    assert row["parent_span_id"] == "p1"
    assert row["principal"] == "alice"
