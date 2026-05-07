"""Detect similar tool NAMES registered with FastMCP.

Adapted from a2atlassian's similar-function-name detector. We flag tool names
with edit-distance < 2 (e.g., `get_issue` vs `get_issues`) as agent-confusing.

Wired into `a2kit check A2KR004` for runtime checks; this script is the
standalone dev-loop hook.

Usage:
    uv run python scripts/find_similar.py --import my_mcp.server:server
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import Any


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _list_tool_names(server: Any) -> list[str]:
    try:
        tools = server._tool_manager.list_tools()  # noqa: SLF001 — pinned FastMCP seam
    except AttributeError:
        return []
    return [getattr(t, "name", "") for t in tools]


def _import_target(spec: str) -> Any:
    if ":" not in spec:
        msg = f"--import requires module:attr, got {spec!r}"
        raise ValueError(msg)
    mod, attr = spec.split(":", 1)
    return getattr(importlib.import_module(mod), attr)


def find_similar(names: list[str], *, threshold: int = 2) -> list[tuple[str, str]]:
    """Return pairs of names whose edit-distance is < threshold."""
    out: list[tuple[str, str]] = [(a, b) for i, a in enumerate(names) for b in names[i + 1 :] if _edit_distance(a, b) < threshold]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find similar tool names registered on a FastMCP server.")
    parser.add_argument("--import", dest="import_target", required=True, help="module:attr")
    parser.add_argument("--threshold", type=int, default=2, help="Edit-distance threshold (default: 2)")
    args = parser.parse_args(argv)

    server = _import_target(args.import_target)
    names = _list_tool_names(server)
    similar = find_similar(names, threshold=args.threshold)
    if not similar:
        print(f"OK: no similar tool names among {len(names)}.")
        return 0
    for a, b in similar:
        print(f"WARN: {a!r} <-> {b!r} (edit-distance < {args.threshold})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
