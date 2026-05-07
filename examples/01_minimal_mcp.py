"""Smallest viable MCP — single Router, one read tool, one write tool.

This is the canonical shape. Real MCPs (a2db, a2atlassian, a2web) start here
and grow.

v0.9 ergonomics:
- `connection: str` is auto-injected into the agent-facing schema for any
  `@Router.read/.write` tool. The agent picks `connection="prod"` etc.
- The resolved `ConnectionInfo` subclass is auto-injected into the function
  via the typed parameter (`info: WidgetConn`). Type-driven DI; no plumbing.
- `@Router.tool()` is the no-connection escape hatch.

The tool body declares zero connection-management code. The kit handles
lookup, ${ENV} resolution, read-only enforcement, and the agent-facing key.

Run as MCP: `uv run python examples/01_minimal_mcp.py serve`
Run CLI: `uv run python examples/01_minimal_mcp.py login prod --field url=https://api --field token='${WIDGET_TOKEN}'`
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import a2kit


class WidgetConn(a2kit.ConnectionInfo):
    """Saved per-environment Widgets API credential."""

    url: str
    token: str
    read_only: bool = True


class WidgetsRouter(a2kit.Router):
    """Routes every Widgets-related tool. Slug auto-derived: `widgets`."""


@WidgetsRouter.read()
async def list_widgets(info: WidgetConn) -> list[dict]:
    """List widgets."""
    # `info` is the resolved + token-resolved WidgetConn. Agent calls with
    # `connection="prod"`; the kit binds the resolved info here.
    return [{"id": 1, "url": info.url}, {"id": 2, "url": info.url}]


@WidgetsRouter.write()
async def create_widget(info: WidgetConn, name: str) -> dict:
    """Create a widget. Refused if `info.read_only` is True."""
    return {"id": 99, "name": name, "url": info.url}


def build_app() -> tuple[FastMCP, a2kit.ConnectionStore[WidgetConn], a2kit.RouterRegistry]:
    """Wire FastMCP + store + Router. Lifted into a function so the CLI and
    the `serve` command share the same plumbing."""
    config_dir = Path.home() / ".config" / "a2widgets"
    config_dir.mkdir(parents=True, exist_ok=True)
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(config_dir, WidgetConn)
    server = FastMCP("a2widgets")
    registry = a2kit.RouterRegistry()
    registry.add(WidgetsRouter(store=store))
    return server, store, registry


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    server, store, registry = build_app()

    cli = a2kit.build_cli(store, name="a2widgets")

    @cli.command("serve")
    def _serve() -> None:
        """Start the MCP. Runs stdio by default; `--http :7000` switches transport."""
        a2kit.MCPRunner(server, store=store, router_registry=registry).run(argv=[])

    cli(args=args, standalone_mode=False)


if __name__ == "__main__":  # pragma: no cover
    tmp = Path(tempfile.mkdtemp())
    a2kit.ConnectionStore(tmp, WidgetConn).save(WidgetConn(key=("prod",), url="https://api.example", token="${WIDGET_TOKEN}"))
    print(f"Demo connection saved at {tmp}.")
    print("In prod, run `python 01_minimal_mcp.py login prod --field url=... --field token=...` first.")
