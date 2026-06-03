"""Capability: a domain filter selects rows from the thin jsonl columns
without opening any blob sidecar — the scan-light, query-fast property.
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


def test_domain_filter_reads_thin_rows_only(tmp_path: Path) -> None:
    handler = CallLogFileHandler(log_dir=tmp_path, inline_threshold=16)
    _emit(handler, CallRecord(call_id="a", tool="ask", domain="x.com", principal=None, elapsed_ms=1, args={}, result="X" * 100))
    _emit(handler, CallRecord(call_id="b", tool="ask", domain="y.com", principal=None, elapsed_ms=1, args={}, result="Y" * 100))
    handler.close()

    files = sorted((tmp_path / "calls").glob("*.jsonl"))
    rows = [json.loads(line) for f in files for line in f.read_text().splitlines()]
    matched = [r for r in rows if r["domain"] == "x.com"]

    assert len(matched) == 1
    assert matched[0]["call_id"] == "a"
    # domain selection touched only the thin row; the body lives behind a hash.
    assert "result" not in matched[0]
    assert "result_hash" in matched[0]
