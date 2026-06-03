"""Mirror unit tests for ``a2kit.packages.log.call_log``."""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.log.call_log import CallRecord, _content_address


def test_call_record_to_row_orders_span_columns_then_bodies() -> None:
    row = CallRecord(call_id="c1", tool="ask", domain="x.com", elapsed_ms=3, args={"a": 1}, result="r").to_row()
    assert row["call_id"] == "c1"
    assert row["tool"] == "ask"
    assert row["domain"] == "x.com"
    assert row["args"] == {"a": 1}
    assert row["result"] == "r"


def test_content_address_replaces_large_string_with_hash(tmp_path: Path) -> None:
    bodies = tmp_path / "bodies"
    out = _content_address({"result": "z" * 50, "tool": "ask"}, bodies, inline_threshold=10)
    assert "result" not in out
    assert "result_hash" in out
    assert out["tool"] == "ask"
    assert (bodies / out["result_hash"]).read_text() == "z" * 50


def test_content_address_dedupes_identical_bodies(tmp_path: Path) -> None:
    bodies = tmp_path / "bodies"
    h1 = _content_address({"a": "q" * 50}, bodies, inline_threshold=10)["a_hash"]
    h2 = _content_address({"b": "q" * 50}, bodies, inline_threshold=10)["b_hash"]
    assert h1 == h2
    assert len(list(bodies.iterdir())) == 1
