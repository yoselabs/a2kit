"""Example: `build_cli` + `MCPRunner` — the canonical v0.2 entrypoint pair.

Demonstrates:
- `build_cli(...)` returns a Click group with login/logout/connections list/show/delete.
- `MCPRunner` absorbs `--register` / `--scope` / `--select` / `--http` parsing
  AND transport selection in one call.

Run:
  `uv run python examples/scaffold_cli.py --help`
  `uv run python examples/scaffold_cli.py serve --register myconn url=https://x token=t email=e`
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import click

import a2kit


class MyConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str
    email: str
    token: str


class _FakeServerSettings:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 8000


class _FakeServer:
    """Stand-in for FastMCP so the example doesn't bind a port."""

    def __init__(self) -> None:
        self.settings = _FakeServerSettings()
        self.tools: list[str] = []

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools.append(fn.__name__)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        click.echo(f"would-run server transport={transport} host={self.settings.host} port={self.settings.port}")


def main() -> None:
    config_dir = Path(tempfile.mkdtemp())
    store: a2kit.ConnectionStore[MyConn] = a2kit.ConnectionStore(config_dir, MyConn)

    cli = a2kit.scaffold.build_cli(store, name="a2example")

    @cli.command("serve")
    def serve() -> None:
        """Start an MCP server using MCPRunner."""
        runner = a2kit.scaffold.MCPRunner(_FakeServer(), store=store)
        # Strip the `serve` token before MCPRunner sees argv.
        argv = [a for a in sys.argv[1:] if a != "serve"]
        runner.run(argv=argv)

    cli(standalone_mode=False)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.extend(["--help"])
    import contextlib

    with contextlib.suppress(click.exceptions.Exit, SystemExit):
        main()
