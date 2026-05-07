"""Example: v0.3.1 `Router` (Pydantic) with capabilities + auto-tag.

Run: `uv run python examples/router_class.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import a2kit
from a2kit import Cap, Router, RouterRegistry


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    base_url: str


class _FakeManager:
    def __init__(self) -> None:
        self._tools: list[Any] = []

    def list_tools(self) -> list[Any]:
        return list(self._tools)


class _FakeServer:
    def __init__(self) -> None:
        self._tool_manager = _FakeManager()
        self.settings = type("S", (), {"host": "127.0.0.1", "port": 8000})()

    def tool(self, *_a, **_kw):
        def deco(fn):
            t = type("T", (), {"name": fn.__name__, "fn": fn})()
            self._tool_manager._tools.append(t)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        print(f"would-run server transport={transport}")


class IssuesRouter(Router):
    """Router subclass — tools registered here auto-carry `issues` + read/write tags."""

    def register_read(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="connection")
        async def list_issues(connection: str, *, info: WidgetConn | None = None) -> dict:
            assert info is not None
            return {"issues": [], "url": info.base_url}

    def register_write(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="connection", write=True)
        async def create_issue(connection: str, *, info: WidgetConn | None = None) -> dict:
            return {"created": True}


def main() -> None:
    config_dir = Path(tempfile.mkdtemp())
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(config_dir, WidgetConn)
    store.save(WidgetConn(key=("prod",), base_url="https://api"))
    server = _FakeServer()

    registry = RouterRegistry()
    registry.add(IssuesRouter(name="issues", default=True, capabilities={Cap.EXTERNAL}))

    runner = a2kit.scaffold.MCPRunner(server, store=store, router_registry=registry)
    runner.run(argv=["--select", "default and not destructive"])

    print("registered:")
    for t in server._tool_manager.list_tools():
        caps = sorted(t.fn._a2kit_capabilities)
        print(f"  {t.name}: caps={caps}")


if __name__ == "__main__":
    main()
