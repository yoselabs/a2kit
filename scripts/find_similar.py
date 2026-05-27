"""Detect similar tool NAMES registered with FastMCP.

Adapted from a Jira/Confluence-wrapping MCP's similar-function-name detector. We flag tool names
with edit-distance < 2 (e.g., `get_issue` vs `get_issues`) as agent-confusing.

Wired into `a2kit check A2KR004` for runtime checks; this script is the
standalone dev-loop hook.

Usage:
    uv run python scripts/find_similar.py --import my_mcp.server:server
"""

from __future__ import annotations

import argparse
import sys

from a2kit.packages.lint._distance import edit_distance
from a2kit.packages.lint._import import import_target
from a2kit.packages.lint.runtime import list_tool_names


def find_similar(names: list[str], *, threshold: int = 2) -> list[tuple[str, str]]:
    """Return pairs of names whose edit-distance is < threshold."""
    return [(a, b) for i, a in enumerate(names) for b in names[i + 1 :] if edit_distance(a, b) < threshold]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find similar tool names registered on a FastMCP server.")
    parser.add_argument("--import", dest="import_target", required=True, help="module:attr")
    parser.add_argument("--threshold", type=int, default=2, help="Edit-distance threshold (default: 2)")
    args = parser.parse_args(argv)

    server = import_target(args.import_target)
    names = list_tool_names(server)
    similar = find_similar(names, threshold=args.threshold)
    if not similar:
        print(f"OK: no similar tool names among {len(names)}.")
        return 0
    for a, b in similar:
        print(f"WARN: {a!r} <-> {b!r} (edit-distance < {args.threshold})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
