"""In-process tool invocation: enricher wrap, format dispatch."""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.packages.cli.runtime import _invoke_tool_in_process, invoke_tool_sync


@a2kit.read()
def simple_tool(*, n: int) -> dict:
    return {"value": n * 2}


@a2kit.read()
async def async_tool(*, n: int) -> dict:
    return {"value": n + 1}


def test_invoke_sync_returns_formatter_data() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 3}, fmt="json")
    assert out == '{"value":6}'


def test_invoke_async_runs_coroutine() -> None:
    out = invoke_tool_sync(async_tool, {"n": 4}, fmt="json")
    assert out == '{"value":5}'


def test_format_auto_picks_json_for_flat_dict() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 7}, fmt="auto")
    # Flat dict → json
    assert out == '{"value":14}'


def test_format_toon_forced() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 2}, fmt="toon")
    # Just confirm it differs from JSON form (TOON encoding present).
    assert out != '{"value":4}'


def test_enricher_wraps_exceptions() -> None:
    """Class-attribute ``enrichers`` are applied by the CLI builder."""

    class BoomError(Exception):
        pass

    def enrich(exc: Exception) -> str | None:
        if isinstance(exc, BoomError):
            return "nicer message"
        return None

    class R(a2kit.Router):
        enrichers = [enrich]

        @a2kit.read()
        def boom(self, *, x: int) -> dict:
            raise BoomError("ugly")

    # Builder applies enrichers; here we apply manually using the same wrapper.
    from a2kit.packages.cli.builder import _wrap_with_enricher

    router = R()
    bound = router.tools()[0]
    enriched = _wrap_with_enricher(bound, router)

    with pytest.raises(BoomError, match="nicer message"):
        invoke_tool_sync(enriched, {"x": 1}, fmt="json")


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
