"""Example: v0.3 `Feature` is now a deprecated alias of v0.3.1 `Router`.

This example shows the migration path: same shape, but instantiated via
keyword args (Pydantic) instead of class-level attribute assignments.

Run: `uv run python examples/feature_class.py`
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from a2kit.scaffold import Feature, Router, RouterRegistry


class _IssuesEnricher:
    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if isinstance(exc, KeyError):
            return RuntimeError(f"Issue not found (tool: {tool_name}): {exc}")
        return exc


class IssuesRouter(Router):
    """Router subclass — instantiate with `name=...` etc. (no class-attr syntax)."""

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

    # Demonstrate the deprecated `Feature` alias still works (one cycle):
    with warnings.catch_warnings():
        warnings.simplefilter("default", DeprecationWarning)

        class _Legacy(Feature):
            pass

        legacy = _Legacy(name="legacy", default=False)
        print(f"legacy router via Feature alias: {legacy.name} (deprecated)")


if __name__ == "__main__":
    main()
