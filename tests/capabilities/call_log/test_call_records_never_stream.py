"""Capability (§1.8): the topology guarantee.

The dedicated ``a2kit.calls`` logger has ``propagate=False`` and the wire +
stdout handlers are NOT attached to it, so an auto call-record can never reach
the agent stream. A ``debug`` enrichment row is kept off the wire by level
(wire defaults to INFO+). Both still land in the call-log file.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import a2kit
import a2kit.log
from a2kit.config import A2kitConfig, LogConfig
from a2kit.testing import client


def _app(tmp: Path) -> a2kit.App:
    cfg = A2kitConfig(log=LogConfig(call_log="on", call_log_dir=str(tmp)))

    class R(a2kit.Router):
        slug = "r"

        @a2kit.read()
        async def work(self, *, url: str) -> dict[str, str]:
            await a2kit.log.debug("secret-blob", body="s3cr3t")
            return {"ok": url}

    return a2kit.App("topology", config=cfg).add_router(R())


def test_call_record_and_debug_never_reach_the_wire(tmp_path: Path) -> None:
    app = _app(tmp_path)

    async def go() -> object:
        async with client(app) as c:
            await c.invoke("r_work", url="https://x.com")
            return c

    c = asyncio.run(go())

    # Nothing the agent sees mentions the durable record or the debug blob.
    wire_blob = json.dumps([c.logs, getattr(c, "events", []), getattr(c, "reports", [])])
    assert "s3cr3t" not in wire_blob
    assert "secret-blob" not in wire_blob

    # But the call-log file captured the record AND the debug row.
    files = sorted((tmp_path / "calls").glob("*.jsonl"))
    text = "\n".join(f.read_text() for f in files)
    assert "secret-blob" in text
    assert "s3cr3t" in text


def test_calls_logger_does_not_propagate() -> None:
    # Structural invariant, independent of any per-handler level config.
    assert logging.getLogger("a2kit.calls").propagate is False
