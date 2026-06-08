"""BDD: sandboxed `call_tool` carries connection scope + DI (code-execution-surface §5).

Promotes `docs/SPIKE_CODE_EXEC_DI.md` into a permanent real-transport
test: the sandbox's `call_tool` runs an a2kit tool whose `store` is
DI-resolved from the wire `connection`, routed through the gated
`A2kitCodeMode` transform.
"""

from __future__ import annotations

import asyncio
import importlib
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

import a2kit
from a2kit.packages.mcp.server import build_mcp_server


@pytest.fixture
def tracker_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> a2kit.App:
    """The tracker example wired to a temp connection + seeded DB."""
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "connections"))

    import examples.tracker.connection as conn_mod
    import examples.tracker.models as models_mod
    import examples.tracker.routers as routers_mod
    import examples.tracker.server as srv
    import examples.tracker.store as store_mod

    importlib.reload(conn_mod)
    importlib.reload(store_mod)
    importlib.reload(routers_mod)
    importlib.reload(srv)

    from a2kit.packages.connections.store import ConnectionStore

    db_path = tmp_path / "tracker.jsonl"
    conn = conn_mod.TrackerConn(key=("default",), db_path=str(db_path))
    asyncio.run(ConnectionStore(conn_mod.TrackerConn).save(conn))
    store_mod.TrackerStore(conn).replace(
        [models_mod.Project(id="p1", name="Spike")],
        [models_mod.Task(id="t1", project_id="p1", title="First task")],
    )
    return srv.app


@pytest.mark.asyncio
async def test_sandbox_call_tool_carries_connection_and_di(tracker_app: a2kit.App) -> None:
    """Sandboxed `call_tool` with a `connection` resolves the connection-scoped DI tool."""
    server = build_mcp_server(tracker_app)
    code = 'await call_tool("tasks_list_tasks", {"connection": "default"})'
    async with Client(server) as c:
        result = await c.call_tool("execute", {"code": code})
    data = result.data if result.data is not None else result.content
    assert "First task" in str(data)


@pytest.mark.asyncio
async def test_sandbox_missing_connection_fails_legibly(tracker_app: a2kit.App) -> None:
    """A sandboxed call to a connection-scoped tool without `connection` fails clearly.

    `mask_error_details=False` surfaces the inner validation detail on the
    wire; with masking on (the default) the call still fails as `ToolError`,
    just with a generic message.
    """
    server = build_mcp_server(tracker_app, mask_error_details=False)
    code = 'await call_tool("tasks_list_tasks", {})'
    async with Client(server) as c:
        with pytest.raises(ToolError) as exc:
            await c.call_tool("execute", {"code": code})
    assert "connection" in str(exc.value).lower()
