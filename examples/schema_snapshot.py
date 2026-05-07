"""Example: schema snapshot + per-tool token-budget read.

Demonstrates:
- A small FastMCP server with two tools.
- `snapshot_schemas(server, dir)` writes one compact-JSON file per tool.
- `os.path.getsize(...)` on each file is the byte-accurate token-budget proxy.
- `assert_schemas_match(...)` would fail on drift; running it twice in a row
  passes here because schemas are identical.

Run: `uv run python examples/schema_snapshot.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import a2kit


def main() -> None:
    server = FastMCP("widgets")

    @server.tool()
    def get_widget(widget_id: int) -> dict:
        """Fetch a widget by id."""
        return {"id": widget_id}

    @server.tool()
    def list_widgets(limit: int = 50, offset: int = 0) -> dict:
        """Paginated widget list."""
        return {"items": [], "limit": limit, "offset": offset}

    snapshot_dir = Path(tempfile.mkdtemp()) / "schemas"
    paths = a2kit.testing.snapshot_schemas(server, snapshot_dir)

    print(f"Wrote {len(paths)} snapshots to {snapshot_dir}")
    for name, path in paths.items():
        size = path.stat().st_size
        print(f"  {name}: {size} bytes")

    a2kit.testing.assert_schemas_match(server, snapshot_dir)
    print("assert_schemas_match passed (no drift).")


if __name__ == "__main__":
    main()
