"""Example: minimum viable v0.7 MCP — `StrEnum Cap`, no `info` kwarg, plain
docstrings (auto-injected), `WidgetsRouter.context.info()` accessor.

v0.7 changes vs v0.6:

- `Cap` is `StrEnum`. `list(Cap)` works; `Cap("write")` parses raw strings.
- The `*, info: ConnT | None = None` kwarg pattern is gone — only path is
  `WidgetsRouter.context.info()`.
- Param doc is auto-injected at decoration time. The plain triple-quoted
  docstring below grows the canonical `connection: ...` line automatically.

Run: `uv run python examples/v07_minimal_mcp.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import a2kit
from a2kit import Cap


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
    url: str


class WidgetsRouter(a2kit.Router):
    pass


@WidgetsRouter.read(connection_param="conn")
async def list_widgets(conn: str) -> list[dict]:
    """List widgets for the given connection."""
    info = WidgetsRouter.context.info()  # typed access — only API in v0.7
    return [{"conn": conn, "url": getattr(info, "url", "")}]


@WidgetsRouter.write(connection_param="conn")
async def create_widget(conn: str, name: str) -> dict:
    """Create a widget."""
    return {"conn": conn, "name": name, "ok": True}


def main() -> None:
    print(f"Cap members: {list(Cap)}")
    print(f"Cap.WRITE == 'write': {Cap.WRITE == 'write'}")
    print(f"Cap('write') parses: {Cap('write')}")

    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(WidgetConn(key=("prod",), url="https://api"))

    server = _FakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(WidgetsRouter(store=store))

    a2kit.MCPRunner(server, store=store, router_registry=routers).run(argv=[])


if __name__ == "__main__":
    main()
