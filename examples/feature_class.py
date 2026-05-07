"""Example: v0.3 `Feature` base class with enricher, snapshot_dir, register_read/write.

Run: `uv run python examples/feature_class.py`
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from a2kit.scaffold import Feature, FeatureRegistry


class _IssuesEnricher:
    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if isinstance(exc, KeyError):
            return RuntimeError(f"Issue not found (tool: {tool_name}): {exc}")
        return exc


class IssuesFeature(Feature):
    """Feature module bundling enricher + register hooks + snapshot dir."""

    name = "issues"
    default = True
    enricher = _IssuesEnricher()
    snapshot_dir = Path("__snapshots__/issues")
    cassette_dir = Path("__cassettes__/issues")

    def register_read(self, server: Any, store: Any) -> None:
        server.tools.append("issues:get_issue")
        server.tools.append("issues:search_issues")

    def register_write(self, server: Any, store: Any) -> None:
        server.tools.append("issues:create_issue")


class _Server:
    tools: list[str] = []  # noqa: RUF012


def main() -> None:
    reg = FeatureRegistry()
    reg.add(IssuesFeature())

    server = _Server()
    server.tools = []
    applied = reg.apply(server, None, include_writes=True)
    print(f"applied features: {applied}")
    print(f"registered tools: {server.tools}")
    print(f"feature snapshot_dir: {IssuesFeature.snapshot_dir}")
    print(f"feature enricher: {type(IssuesFeature.enricher).__name__}")


if __name__ == "__main__":
    main()
