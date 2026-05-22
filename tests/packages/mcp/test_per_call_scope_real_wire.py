"""BDD: per-call scope flows through the real MCP wire (dispatch-lifecycle-wiring).

Covers spec ``request-scoped-di``: when a tool dispatched via
``fastmcp.Client(transport=build_mcp_server(app))`` resolves a
``per_call=True`` provider, the resource enters during the call and
its ``__aexit__`` runs exactly once when the call completes — with
the propagating body exception forwarded through standard async-with
semantics.

Implementation arrives in §3 of the dispatch-lifecycle-wiring task list;
until then these tests fail because the MCP wrapper still uses the
legacy "hook returns kwargs" path that bypasses ``Container.dispatch``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


class _Transaction:
    enter_count: int = 0
    exit_count: int = 0
    last_exc_type: type[BaseException] | None = None

    async def __aenter__(self) -> _Transaction:
        type(self).enter_count += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        type(self).exit_count += 1
        type(self).last_exc_type = exc_type


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Transaction.enter_count = 0
    _Transaction.exit_count = 0
    _Transaction.last_exc_type = None


def _build_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def use_tx(self, tx: _Transaction) -> dict[str, Any]:
            return {"tx_id": id(tx)}

        @a2kit.read()
        async def boom_with_tx(self, tx: _Transaction) -> dict[str, Any]:
            raise ValueError("boom")

        tools = (use_tx, boom_with_tx)

    return a2kit.AppBuilder("per-call-mcp").add_router(R()).provide(_Transaction, per_call=True).build()


@pytest.mark.asyncio
async def test_per_call_resource_cleaned_up_at_mcp_call_exit() -> None:
    """One MCP tool call enters Transaction once, exits once on clean return."""
    app = _build_app()
    async with app, Client(transport=build_mcp_server(app)) as c:
        await c.call_tool("use_tx", {})

    assert _Transaction.enter_count == 1, f"Transaction entered {_Transaction.enter_count} times — expected 1"
    assert _Transaction.exit_count == 1, f"Transaction exited {_Transaction.exit_count} times — expected 1"
    assert _Transaction.last_exc_type is None, "__aexit__ saw an exception on a clean return"


@pytest.mark.asyncio
async def test_per_call_resource_sees_body_exception_on_aexit() -> None:
    """Tool body raise propagates the exception to __aexit__'s exc_type arg."""
    app = _build_app()
    async with app, Client(transport=build_mcp_server(app)) as c:
        with pytest.raises(ToolError) as excinfo:
            await c.call_tool("boom_with_tx", {})
        # Body exception surfaces on the wire envelope.
        payload = json.loads(str(excinfo.value))
        assert payload["class"] == "ValueError"
        assert payload["message"] == "boom"

    assert _Transaction.exit_count == 1
    assert _Transaction.last_exc_type is ValueError, f"__aexit__ saw {_Transaction.last_exc_type!r}; expected ValueError"
