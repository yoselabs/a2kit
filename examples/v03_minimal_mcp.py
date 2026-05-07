"""Example: shortest working v0.3.1 MCP — using Router + --select + Cap constants.

Run: `uv run python examples/v03_minimal_mcp.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import a2kit


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    base_url: str


class _FakeManager:
    def __init__(self) -> None:
        self._tools: list[Any] = []

    def list_tools(self) -> list[Any]:
        return list(self._tools)


class _FakeServer:
    """Stand-in for FastMCP — keeps the example hermetic."""

    def __init__(self) -> None:
        self._tool_manager = _FakeManager()
        self.settings = type("S", (), {"host": "127.0.0.1", "port": 8000})()

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            t = type("T", (), {"name": fn.__name__, "fn": fn})()
            self._tool_manager._tools.append(t)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        print(f"would-run server transport={transport}")


def main() -> None:
    config_dir = Path(tempfile.mkdtemp())
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(config_dir, WidgetConn)
    store.save(WidgetConn(key=("prod",), base_url="https://api"))
    server = _FakeServer()

    @a2kit.tool(server=server, store=store, connection_param="connection", capabilities={a2kit.Cap.EXTERNAL})
    async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
        """Fetch one widget."""
        assert info is not None
        return {"id": widget_id, "url": info.base_url}

    @a2kit.tool(server=server, store=store, connection_param="connection", write=True, capabilities={a2kit.Cap.DESTRUCTIVE})
    async def update_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
        """Update one widget."""
        assert info is not None
        return {"id": widget_id, "updated": True}

    print(f"registered: {[t.name for t in server._tool_manager.list_tools()]}")
    # `--select` carries the boolean expression; default = read-only, non-destructive.
    a2kit.scaffold.MCPRunner(server, store=store).run(argv=["--select", "default and not destructive"])


if __name__ == "__main__":
    main()
