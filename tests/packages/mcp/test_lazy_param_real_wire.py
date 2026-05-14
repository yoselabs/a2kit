"""BDD: ``Lazy[T]`` skips resource entry under the real MCP wire.

Covers spec ``request-scoped-di``: a tool parameter typed ``Lazy[T]``
that the body never awaits MUST NOT cause ``T.__aenter__`` to run,
even when dispatched through the production MCP wrapper chain.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client

import a2kit
from a2kit.packages.di import Lazy
from a2kit.packages.mcp.server import build_mcp_server


class _Browser:
    enter_count: int = 0
    exit_count: int = 0

    async def __aenter__(self) -> _Browser:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).exit_count += 1


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Browser.enter_count = 0
    _Browser.exit_count = 0


@pytest.mark.asyncio
async def test_lazy_never_invoked_resource_not_entered_under_mcp() -> None:
    """Tool body never awaits ``browser()`` → ``Browser.__aenter__`` never runs."""

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def skip_browser(self, browser: Lazy[_Browser]) -> dict[str, Any]:
            # Intentionally do NOT await browser().
            return {"used": False}

        tools = (skip_browser,)

    app = a2kit.App("lazy-mcp")
    app.add_router(R())
    app.provide(_Browser)  # app-scope

    async with app, Client(transport=build_mcp_server(app)) as c:
        await c.call_tool("skip_browser", {})

    assert _Browser.enter_count == 0, (
        f"Browser.__aenter__ ran {_Browser.enter_count} times despite Lazy not awaited"
    )
    assert _Browser.exit_count == 0
