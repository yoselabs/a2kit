"""In-process CLI tool invocation: pipeline fold, format dispatch, error render."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import typer

import a2kit
from a2kit.metadata import get_meta
from a2kit.packages.cli.runtime import _invoke_tool_in_process, invoke_tool_sync
from a2kit.packages.dispatch import ToolBuildSpec


@a2kit.read()
def simple_tool(*, n: int) -> dict:
    return {"value": n * 2}


@a2kit.read()
async def async_tool(*, n: int) -> dict:
    return {"value": n + 1}


def _spec(fn: Any, *, app: a2kit.App | None = None, router: Any = None) -> ToolBuildSpec:
    """Build a `ToolBuildSpec` for a standalone or router-bound tool."""
    return ToolBuildSpec(
        app=app if app is not None else a2kit.App("runtime-test"),
        router=router,
        meta=get_meta(fn),
    )


def test_invoke_sync_returns_formatter_data() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 3}, fmt="json", spec=_spec(simple_tool))
    assert out == '{"value":6}'


def test_invoke_async_runs_coroutine() -> None:
    out = invoke_tool_sync(async_tool, {"n": 4}, fmt="json", spec=_spec(async_tool))
    assert out == '{"value":5}'


def test_format_auto_picks_json_for_flat_dict() -> None:
    out = invoke_tool_sync(simple_tool, {"n": 7}, fmt="auto", spec=_spec(simple_tool))
    assert out == '{"value":14}'


def test_enricher_wraps_exceptions(capsys: pytest.CaptureFixture[str]) -> None:
    """The router's ``enrichers`` are applied by the shared pipeline's
    ``EnricherStage``; the CLI error-render stage then surfaces the
    enriched message on stderr and exits non-zero.
    """

    class BoomError(Exception):
        pass

    def enrich(exc: Exception) -> str | None:
        if isinstance(exc, BoomError):
            return "nicer message"
        return None

    class R(a2kit.Router):
        slug = "r"
        enrichers = [enrich]

        @a2kit.read()
        def boom(self, *, x: int) -> dict:
            raise BoomError("ugly")

        tools = (boom,)

    app = a2kit.App("enricher-runtime")
    app.add_router(R())
    desc = app.tools()[0]
    spec = _spec(desc.fn, app=app, router=app.routers()[0])

    with pytest.raises(typer.Exit):
        invoke_tool_sync(desc.fn, {"x": 1}, fmt="json", spec=spec)
    assert "nicer message" in capsys.readouterr().err


def test_ctx_param_supplied() -> None:
    received: dict = {}

    @a2kit.read()
    def with_ctx(*, n: int, ctx: a2kit.ToolContext) -> dict:
        received["ctx"] = ctx
        return {"n": n}

    out = invoke_tool_sync(with_ctx, {"n": 5}, fmt="json", spec=_spec(with_ctx))
    assert out == '{"n":5}'
    assert received["ctx"] is not None
    assert hasattr(received["ctx"], "info")


def test_async_invoke_in_process() -> None:
    data = asyncio.run(_invoke_tool_in_process(simple_tool, {"n": 1}, fmt="json", spec=_spec(simple_tool)))
    assert data == '{"value":2}'
