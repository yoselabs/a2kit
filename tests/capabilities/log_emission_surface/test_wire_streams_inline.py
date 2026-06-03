"""Capability: a level method streams on the MCP wire inline, mid-call.

The emission primitives are async and the wire emission is an inline
``await ctx.log(...)`` — delivered before the tool returns, never deferred
behind a sync handler. (Full transport integration is exercised in the
dispatch tests; here we assert the inline-await contract at the unit level by
forcing the fastmcp-context branch.)
"""

from __future__ import annotations

from typing import Any

import pytest

from a2kit.log import info
from a2kit.packages.log import emission
from a2kit.packages.log.scope import bind_call_scope


class _FakeCtx:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def log(self, *, level: str, message: str, extra: dict[str, Any]) -> None:
        self.calls.append((level, message, extra))


async def test_info_streams_inline_on_fastmcp_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(emission, "_is_fastmcp_context", lambda _ctx: True)
    ctx = _FakeCtx()
    with bind_call_scope(ctx=ctx, call_id="c1", tool_name="ask"):
        await info("fetching", host="x.com")
    assert len(ctx.calls) == 1
    level, message, extra = ctx.calls[0]
    assert level == "info"
    assert message == "fetching"
    assert extra["host"] == "x.com"
    assert "a2kit_elapsed_ms" in extra


async def test_no_wire_emit_when_ctx_is_not_fastmcp() -> None:
    ctx = _FakeCtx()
    with bind_call_scope(ctx=ctx, call_id="c1"):
        await info("orphan")
    assert ctx.calls == []
