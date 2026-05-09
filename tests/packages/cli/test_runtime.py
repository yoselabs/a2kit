"""In-process tool invocation: enricher wrap, DI strip, format dispatch."""

from __future__ import annotations

import asyncio

import pytest
from uncalled_for import Depends

import a2kit
from a2kit.packages.cli.runtime import _invoke_tool_in_process, invoke_tool_sync


@a2kit.read()
def simple_tool(*, n: int) -> dict:
    return {"value": n * 2}


@a2kit.read()
async def async_tool(*, n: int) -> dict:
    return {"value": n + 1}


def _factory() -> int:
    return 99


@a2kit.read()
def with_di(*, n: int, dep: int = Depends(_factory)) -> dict:
    return {"sum": n + dep}


def test_invoke_sync_returns_formatter_data() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 3}, fmt="json")
    assert out == '{"value":6}'


def test_invoke_async_runs_coroutine() -> None:
    out = invoke_tool_sync(async_tool, {"n": 4}, fmt="json")
    assert out == '{"value":5}'


def test_invoke_strips_di_params() -> None:
    # Without DI strip, the call would fail because no `dep` passed.
    out = invoke_tool_sync(with_di, {"n": 1}, fmt="json")
    assert out == '{"sum":100}'


def test_format_auto_picks_json_for_flat_dict() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 7}, fmt="auto")
    # Flat dict → json
    assert out == '{"value":14}'


def test_format_toon_forced() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 2}, fmt="toon")
    # Just confirm it differs from JSON form (TOON encoding present).
    assert out != '{"value":4}'


def test_enricher_wraps_exceptions() -> None:
    class BoomError(Exception):
        pass

    class FriendlyError(Exception):
        pass

    def enrich(exc: Exception, _name: str) -> Exception:
        if isinstance(exc, BoomError):
            return FriendlyError("nicer message")
        return exc

    @a2kit.read(enricher=enrich)
    def boom(*, x: int) -> dict:
        raise BoomError("ugly")

    with pytest.raises(FriendlyError, match="nicer message"):
        invoke_tool_sync(boom, {"x": 1}, fmt="json")


def test_ctx_param_supplied() -> None:
    received: dict = {}

    @a2kit.read()
    def with_ctx(*, n: int, ctx: a2kit.ToolContext) -> dict:
        received["ctx"] = ctx
        return {"n": n}

    out = invoke_tool_sync(with_ctx, {"n": 5}, fmt="json", ctx_param_name="ctx")
    assert out == '{"n":5}'
    assert received["ctx"] is not None
    assert hasattr(received["ctx"], "info")


def test_async_invoke_in_process() -> None:
    data = asyncio.run(_invoke_tool_in_process(simple_tool, {"n": 1}, fmt="json"))
    assert data == '{"value":2}'
