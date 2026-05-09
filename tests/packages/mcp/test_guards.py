"""``GuardsMiddleware`` blocks tool-call-contamination strings."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from a2kit.exceptions import ToolCallContamination
from a2kit.packages.mcp.guards import GuardsMiddleware


def _ctx(arguments: dict[str, Any], *, name: str = "tool") -> Any:
    msg = SimpleNamespace(arguments=arguments, name=name)
    return SimpleNamespace(message=msg)


def test_clean_arguments_pass_through() -> None:
    mw = GuardsMiddleware()

    async def call_next(_: Any) -> str:
        return "ok"

    out = asyncio.run(mw.on_call_tool(_ctx({"name": "alice", "n": 5}), call_next))
    assert out == "ok"


def test_contaminated_string_raises() -> None:
    mw = GuardsMiddleware()

    async def call_next(_: Any) -> str:
        return "ok"

    bad = _ctx({"q": "hello <parameter name=foo>bar</parameter>"}, name="search")
    with pytest.raises(ToolCallContamination) as exc:
        asyncio.run(mw.on_call_tool(bad, call_next))
    assert exc.value.param_name == "q"
    assert exc.value.tool_name == "search"


def test_non_string_args_ignored() -> None:
    mw = GuardsMiddleware()

    async def call_next(_: Any) -> str:
        return "ok"

    asyncio.run(mw.on_call_tool(_ctx({"items": [1, 2, 3], "flag": True}), call_next))


def test_empty_arguments_pass_through() -> None:
    mw = GuardsMiddleware()

    async def call_next(_: Any) -> str:
        return "ok"

    asyncio.run(mw.on_call_tool(_ctx({}), call_next))
