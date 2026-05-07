"""Multi-domain MCP — multiple Routers + the `--select` grammar.

This is the shape an Atlassian-flavored MCP takes: one Router per top-level
domain (issues, sprints, comments, …), each with its own read/write tools.
The MCP user picks which subset to expose at runtime via `--select`:

  --select "default and not router:sprints"
  --select "router:issues and write"
  --select "tool:list_issues"

v0.9 ergonomics:
- `capabilities` is a `ClassVar` on the Router subclass — the caps describe
  the router's TYPE, not its runtime config.
- `connection: str` is auto-injected for every `@Router.read/.write` tool.
- The resolved info is bound to the typed `info: JiraConn` param via DI.

Run: `uv run python examples/02_multi_router_mcp.py --select 'default'`
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import ClassVar

from mcp.server.fastmcp import FastMCP

import a2kit
from a2kit import Cap, Capability


class JiraConn(a2kit.ConnectionInfo):
    base_url: str
    email: str
    api_token: str
    read_only: bool = True


class IssuesRouter(a2kit.Router):
    """Slug auto-derived: `issues`."""

    capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}


class SprintsRouter(a2kit.Router):
    """Slug auto-derived: `sprints`. Optional — opted-out at the instance level."""

    capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}


@IssuesRouter.read()
async def list_issues(info: JiraConn, jql: str = "project = WIDGETS") -> list[dict]:
    """Search issues with JQL."""
    return [{"key": "W-1", "url": info.base_url}]


@IssuesRouter.write()
async def create_issue(info: JiraConn, summary: str) -> dict:
    """Create a new issue."""
    return {"key": "W-99", "summary": summary}


@SprintsRouter.read()
async def list_sprints(info: JiraConn) -> list[dict]:
    """List sprints on a board."""
    return [{"id": 1, "name": "Sprint 1"}]


def main(argv: list[str] | None = None) -> None:
    config = Path(tempfile.mkdtemp())
    store: a2kit.ConnectionStore[JiraConn] = a2kit.ConnectionStore(config, JiraConn)
    store.save(
        JiraConn(
            key=("prod",),
            base_url="https://example.atlassian.net",
            email="me@example",
            api_token="${JIRA_TOKEN}",
        )
    )

    server = FastMCP("a2jira")
    registry = a2kit.RouterRegistry()
    registry.add(IssuesRouter())
    registry.add(SprintsRouter(default=False))

    args = sys.argv[1:] if argv is None else argv
    a2kit.MCPRunner(server, store=store, router_registry=registry).run(argv=args)


if __name__ == "__main__":  # pragma: no cover
    main()
