"""Example: minimum viable v0.4 MCP — auto-loaded `default_select`, auto-tagged
Router, `format_response` envelope.

Even shorter than v0.3's minimal. The author owns the FastMCP server; a2kit
threads connections, capabilities, select grammar, and projection.

Run: `uv run python examples/v04_minimal_mcp.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import a2kit


class _FakeServer:
    settings = type("S", (), {"host": "h", "port": 1})()
    tools: list[str] = []  # noqa: RUF012

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools.append(fn.__name__)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        print(f"[run] transport={transport}, tools={self.tools}")


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str


def main() -> None:
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(WidgetConn(key=("prod",), url="https://api"))

    server = _FakeServer()
    routers = a2kit.RouterRegistry()

    class WidgetsRouter(a2kit.Router):
        def register_read(self, server: Any, store: Any) -> None:
            @a2kit.tool(server=server, cel_filter_param="filter", fields_param="fields")
            def list_widgets(filter: str = "", fields: list[str] | None = None) -> list[dict]:  # noqa: A002
                """List widgets, optionally filtered + projected."""
                return [{"name": "alpha", "color": "red"}, {"name": "beta", "color": "blue"}]

    routers.add(WidgetsRouter(name="widgets", default=True))

    # default_select auto-loads from pyproject.toml; no kwarg needed.
    a2kit.MCPRunner(server, store=store, router_registry=routers).run(argv=[])


if __name__ == "__main__":
    main()
