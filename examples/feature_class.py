"""Example: `Router` subclass with enricher + snapshot/cassette dirs.

v0.4: the v0.3 `Feature` alias was removed. Instantiate `Router` (Pydantic
BaseModel) via keyword args.

Run: `uv run python examples/feature_class.py`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from a2kit.scaffold import Router, RouterRegistry


class _IssuesEnricher:
    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if isinstance(exc, KeyError):
            return RuntimeError(f"Issue not found (tool: {tool_name}): {exc}")
        return exc


class IssuesRouter(Router):
    """Router subclass — instantiate with `name=...` etc."""

    def register_read(self, server: Any, store: Any) -> None:
        server.tools.append("issues:get_issue")
        server.tools.append("issues:search_issues")

    def register_write(self, server: Any, store: Any) -> None:
        server.tools.append("issues:create_issue")


class _Server:
    tools: list[str] = []  # noqa: RUF012


def main() -> None:
    reg = RouterRegistry()
    reg.add(
        IssuesRouter(
            name="issues",
            default=True,
            enricher=_IssuesEnricher(),
            snapshot_dir=Path("__snapshots__/issues"),
            cassette_dir=Path("__cassettes__/issues"),
        )
    )

    server = _Server()
    server.tools = []
    applied = reg.apply(server, None, include_writes=True)
    print(f"applied routers: {applied}")
    print(f"registered tools: {server.tools}")


if __name__ == "__main__":
    main()
