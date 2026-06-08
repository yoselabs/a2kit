"""Capability: the call-log captures one access record per dispatch end-to-end.

Drives real tools through the in-process MCP client with the call-log enabled,
then reads the JSONL the boundary stage wrote. Covers auto-capture (§1.5),
opt-in off-by-default (§1.14), per-dispatch call_id isolation (§1.4), and
debug-logging enrichment correlated by call_id (§1.7).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import a2kit
import a2kit.log
from a2kit.config import A2kitConfig, LogConfig
from a2kit.testing import app_of, client


def _app(tmp: Path, *, call_log: str = "on") -> a2kit.App:
    cfg = A2kitConfig(log=LogConfig(call_log=call_log, call_log_dir=str(tmp)))

    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        async def fetch(self, *, url: str) -> dict[str, str]:
            return {"ok": url}

        @a2kit.read()
        async def dig(self, *, url: str) -> dict[str, str]:
            await a2kit.log.debug("html", html="<html>" + "x" * 10 + "</html>")
            return {"ok": url}

    return app_of("calllog", R(), config=cfg)


def _rows(tmp: Path) -> list[dict[str, Any]]:
    files = sorted((tmp / "calls").glob("*.jsonl"))
    return [json.loads(line) for f in files for line in f.read_text().splitlines()]


def test_silent_tool_still_gets_a_call_record(tmp_path: Path) -> None:
    app = _app(tmp_path)

    async def go() -> None:
        async with client(app) as c:
            await c.invoke("r_fetch", url="https://x.com/page")

    asyncio.run(go())
    rows = _rows(tmp_path)
    records = [r for r in rows if r.get("tool") == "r_fetch"]
    assert len(records) == 1
    rec = records[0]
    assert rec["domain"] == "x.com"
    assert rec["args"] == {"url": "https://x.com/page"}
    assert rec["result"] == {"ok": "https://x.com/page"}
    assert isinstance(rec["call_id"], str)
    assert rec["span_id"] is not None


def test_off_by_default_writes_nothing(tmp_path: Path) -> None:
    app = _app(tmp_path, call_log="off")

    async def go() -> None:
        async with client(app) as c:
            await c.invoke("r_fetch", url="https://x.com")

    asyncio.run(go())
    assert not (tmp_path / "calls").exists()


def test_concurrent_calls_get_distinct_call_ids(tmp_path: Path) -> None:
    app = _app(tmp_path)

    async def go() -> None:
        async with client(app) as c:
            await asyncio.gather(
                c.invoke("r_fetch", url="https://a.com"),
                c.invoke("r_fetch", url="https://b.com"),
                c.invoke("r_fetch", url="https://c.com"),
            )

    asyncio.run(go())
    records = [r for r in _rows(tmp_path) if r.get("tool") == "r_fetch"]
    call_ids = {r["call_id"] for r in records}
    assert len(records) == 3
    assert len(call_ids) == 3  # each dispatch minted its own id
    # each record's domain matches its own url arg — no cross-contamination
    for r in records:
        assert r["args"]["url"].split("//")[1].rstrip("/") == r["domain"]


def test_enrichment_is_debug_logging_correlated_by_call_id(tmp_path: Path) -> None:
    app = _app(tmp_path)

    async def go() -> None:
        async with client(app) as c:
            await c.invoke("r_dig", url="https://x.com")

    asyncio.run(go())
    rows = _rows(tmp_path)
    record = next(r for r in rows if r.get("tool") == "r_dig" and "args" in r)
    debug_row = next(r for r in rows if r.get("msg") == "html")
    # The debug enrichment row carries the SAME call_id as the auto record,
    # so a DuckDB GROUP BY call_id reconstructs the full call.
    assert debug_row["call_id"] == record["call_id"]
    # The logged field rides the row directly (content-addressed to html_hash
    # only above the inline threshold).
    assert "html" in debug_row or "html_hash" in debug_row
