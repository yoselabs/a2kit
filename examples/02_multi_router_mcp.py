"""Multi-domain MCP — multiple Routers + the `--select` grammar.

This is the shape an Atlassian-flavored MCP takes: one Router per top-level
domain (issues, sprints, comments, …), each with its own `read`/`write` tools.
The MCP user picks which subset to expose at runtime via `--select`:

  --select "default and not router:sprints"   # everything except sprints
  --select "router:issues and write"          # only Issues writes
  --select "tool:list_issues"                 # one tool by name

Tags are auto-applied by the decorators. Author writes domain code; capability
tagging is mechanical.

Run: `uv run python examples/02_multi_router_mcp.py --select 'default'`
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import a2kit
from a2kit import Cap


class JiraConn(a2kit.ConnectionInfo):
    base_url: str
    email: str
    api_token: str
    read_only: bool = True


class IssuesRouter(a2kit.Router):
    """Slug auto-derived: `issues`. Capability tag `Cap.EXTERNAL` flows to every tool."""


class SprintsRouter(a2kit.Router):
    """Slug auto-derived: `sprints`. Optional — opted-out by default."""


@IssuesRouter.read(connection_param="conn")
async def list_issues(conn: str, jql: str = "project = WIDGETS") -> list[dict]:
    """Search issues with JQL."""
    info = IssuesRouter.context.info()
    return [{"key": "W-1", "url": info.base_url}]


@IssuesRouter.write(connection_param="conn")
async def create_issue(conn: str, summary: str) -> dict:
    """Create a new issue."""
    return {"key": "W-99", "summary": summary}


@SprintsRouter.read(connection_param="conn")
async def list_sprints(conn: str) -> list[dict]:
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
    registry.add(IssuesRouter(capabilities={Cap.EXTERNAL}))
    registry.add(SprintsRouter(capabilities={Cap.EXTERNAL}, default=False))

    args = sys.argv[1:] if argv is None else argv
    a2kit.MCPRunner(server, store=store, router_registry=registry).run(argv=args)


if __name__ == "__main__":  # pragma: no cover
    main()
