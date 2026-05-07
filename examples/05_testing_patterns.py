"""Testing patterns — schema snapshots + cassette-based HTTP record/replay.

Two harnesses you'll want from day one on any real MCP:

1. **Schema snapshots** — `snapshot_schemas(server, dir)` writes one
   compact-JSON file per tool. Run it in CI; commit the snapshots; the next
   run calls `assert_schemas_match` and fails on drift. The same files double
   as a token-budget proxy (a tool whose schema crosses N bytes is the canary
   that the agent's input window is about to overflow).

2. **HTTP cassettes** — `@a2kit.testing.cassette(path)` wraps any test in a
   vcrpy context manager. First run records; later runs replay. Lets you ship
   integration tests that hit a real Atlassian/Stripe/whatever once, then run
   forever offline.

Together they catch: silent breaking changes in upstream APIs (cassette
mismatches → re-record), accidental tool schema drift (snapshot mismatch),
and tool-input bloat (snapshot file size).

Run: `uv run python examples/05_testing_patterns.py`
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
        print(f"  {name}: {size} bytes  ← token-budget proxy")

    # Run again — assert_schemas_match raises on drift.
    a2kit.testing.assert_schemas_match(server, snapshot_dir)
    print("\nassert_schemas_match passed (no drift).")

    # Cassette wrapper — wraps an HTTP-using callable. First call records,
    # subsequent calls replay. We don't issue a real request here, but the
    # decorator works on async tools too:
    cassette_path = Path(tempfile.mkdtemp()) / "demo.yaml"

    @a2kit.testing.cassette(cassette_path)
    def fetch_external() -> str:
        # In a real test: requests.get("https://api.example/...").
        return "ok"

    print(f"\nCassette wrapper ready at {cassette_path}.")
    print("First call records; subsequent calls replay (offline-safe CI).")


if __name__ == "__main__":
    main()
