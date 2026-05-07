"""Example: `RouterRegistry` with two routers and `--select`.

Run: `uv run python examples/feature_modules.py`
"""

from __future__ import annotations

from typing import Any

import a2kit


class _FakeServer:
    def __init__(self) -> None:
        self.tools: list[str] = []


def main() -> None:
    routers = a2kit.RouterRegistry()

    @routers.router("issues", default=True)
    class IssuesRouter:
        @staticmethod
        def register_read(server: Any, _store: Any) -> None:
            server.tools.append("issues:get_issue")
            server.tools.append("issues:search_issues")

        @staticmethod
        def register_write(server: Any, _store: Any) -> None:
            server.tools.append("issues:create_issue")

    @routers.router("sprints", default=False)
    class SprintsRouter:
        @staticmethod
        def register_read(server: Any, _store: Any) -> None:
            server.tools.append("sprints:get_sprint")

        @staticmethod
        def register_write(server: Any, _store: Any) -> None:
            server.tools.append("sprints:create_sprint")

    print(f"available routers: {routers.names()}")
    print(f"defaults: {routers.defaults()}")

    s1 = _FakeServer()
    routers.apply(s1, None)
    print(f"defaults applied (no writes): {s1.tools}")

    s2 = _FakeServer()
    routers.apply(s2, None, enabled=("issues", "sprints"), include_writes=True)
    print(f"all routers + writes: {s2.tools}")


if __name__ == "__main__":
    main()
