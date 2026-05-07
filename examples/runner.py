"""Example: `MCPRunner` end-to-end with v0.4 flags.

Drives the runner with a fake-server stub so the example is hermetic. The
production wiring is identical — replace `_FakeServer` with your `FastMCP`
instance and `runner.run()` will dispatch to stdio or streamable-http.

Run: `uv run python examples/runner.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import a2kit


class _FakeSettings:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 8000


class _FakeServer:
    def __init__(self) -> None:
        self.settings = _FakeSettings()
        self.tools: list[str] = []

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools.append(fn.__name__)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        print(f"server.run(transport={transport!r}) host={self.settings.host} port={self.settings.port}")


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str


def main() -> None:
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(WidgetConn(key=("prod",), url="https://api"))

    routers = a2kit.RouterRegistry()

    @routers.router("issues", default=True)
    class _Issues:
        @staticmethod
        def register_read(_server: Any, _store: Any) -> None:
            print("registered: issues.read")

    @routers.router("sprints", default=False)
    class _Sprints:
        @staticmethod
        def register_read(_server: Any, _store: Any) -> None:
            print("registered: sprints.read")

    runner = a2kit.MCPRunner(
        _FakeServer(),
        store=store,
        router_registry=routers,
        name="a2widgets",
    )

    print("--- defaults (issues only, stdio): ---")
    runner.run(argv=[])

    print("\n--- enable both via --select, http on :7000, ephemeral: ---")
    a2kit.MCPRunner(
        _FakeServer(),
        store=store,
        router_registry=routers,
    ).run(argv=["--select", "router:issues or router:sprints", "--http", ":7000", "--register", "eph", "url=https://eph.example"])


if __name__ == "__main__":
    main()
