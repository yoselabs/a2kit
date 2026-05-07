"""Example: the fat `@a2kit.tool` decorator with all bells.

Demonstrates connection lookup + token resolution + write enforcement +
xml guard + OTel (left disabled — opt-in via `otel=True` once a provider is set).

Run: `uv run python examples/fat_tool.py`
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import a2kit


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    base_url: str
    api_key: str
    read_only: bool = True


def main() -> None:
    config_dir = Path(tempfile.mkdtemp())
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(config_dir, WidgetConn)
    store.save(WidgetConn(key=("prod",), base_url="https://api", api_key="${WIDGET_KEY}"))
    store.save(WidgetConn(key=("rw",), base_url="https://api", api_key="${WIDGET_KEY}", read_only=False))

    os.environ.setdefault("WIDGET_KEY", "real-secret")

    server = FastMCP("widgets")

    # Read tool — zero boilerplate inside the body.
    @server.tool()
    @a2kit.tool(store=store, connection_param="connection")
    async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
        """Fetch a widget. The decorator handles connection lookup, token resolution, XML guard."""
        assert info is not None
        return {"id": widget_id, "url": info.base_url, "key_resolved": info.api_key}

    # Write tool — read-only-by-default. `prod` is read-only; `rw` allows it.
    @server.tool()
    @a2kit.tool(store=store, connection_param="connection", write=True)
    async def update_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
        """Mutating tool. Marks `write=True` — fails on read-only conns."""
        assert info is not None
        return {"id": widget_id, "updated": True}

    print("get_widget(prod):", asyncio.run(get_widget("prod", "alpha")))
    print("update_widget(rw):", asyncio.run(update_widget("rw", "alpha")))
    try:
        asyncio.run(update_widget("prod", "alpha"))
    except a2kit.WriteNotAllowed as exc:
        print("update_widget(prod) -> blocked:", exc)
    try:
        asyncio.run(get_widget("prod", '<parameter name="x">leak'))
    except a2kit.ToolXMLContamination as exc:
        print("xml-guard caught contamination:", exc)


if __name__ == "__main__":
    main()
