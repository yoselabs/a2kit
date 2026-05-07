"""Token-budget control — `projection=True` for list-returning tools.

Large list responses blow agent context windows. The fix: let the agent ask for
a CEL filter and a field projection inline, and post-process server-side. The
v0.8 `projection=True` flag does this with zero plumbing — the decorator
auto-injects `filter: str` and `fields: list[str] | None` keyword-only params
into the tool's MCP-exposed signature.

Without `projection=True`, the same effect costs you (a) declaring the params
on the function and (b) wiring `cel_filter_param=` / `fields_param=` strings.

When the agent calls the tool with `filter` or `fields` set, the result is
wrapped in a typed `Response` envelope — `format`, `data`, `truncated`,
`next_cursor` (reserved for v0.9 pagination). When neither is set, the raw
result passes through.

Run: `uv run python examples/03_projection_tool.py`
"""

from __future__ import annotations

import a2kit

_ISSUES = [
    {"id": 1, "title": "Login broken", "status": "open", "priority": "P1"},
    {"id": 2, "title": "Slow dashboard", "status": "open", "priority": "P3"},
    {"id": 3, "title": "Spelling fix", "status": "closed", "priority": "P4"},
]


@a2kit.tool(projection=True)
def list_issues() -> list[dict]:
    """Return all issues. The agent can `filter` by CEL and project `fields`."""
    return _ISSUES


def main() -> None:
    # No filter, no fields → raw passthrough (untouched).
    print("raw:", list_issues())

    # Filter only — wraps result in a Response envelope (TOON for uniform rows).
    open_issues = list_issues(filter="status == 'open'")  # type: ignore[call-arg]
    print(f"\nopen issues, format={open_issues.format}:")
    print(open_issues.data)

    # Filter + fields — projects the row, drops the rest.
    summary = list_issues(filter="priority == 'P1'", fields=["id", "title"])  # type: ignore[call-arg]
    print(f"\nP1 only, projected:\n{summary.data}")

    # Note the typed envelope:
    print("\nResponse fields:", summary.model_dump())


if __name__ == "__main__":
    main()
