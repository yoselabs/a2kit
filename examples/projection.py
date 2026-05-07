"""Example: CEL projection / filter primitive (v0.4).

Demonstrates:
1. `a2kit.projection.filter_records` — filter rows by a CEL boolean expression.
2. `a2kit.projection.project_fields` — keep only the named keys per row.
3. `a2kit.format_response(data, filter=..., fields=...)` — composed.

Run: `uv run python examples/projection.py`
"""

from __future__ import annotations

import a2kit


def main() -> None:
    issues = [
        {"id": 1, "status": "open", "priority": 5, "title": "Index out of range"},
        {"id": 2, "status": "closed", "priority": 2, "title": "Typo in docs"},
        {"id": 3, "status": "open", "priority": 1, "title": "Minor styling"},
        {"id": 4, "status": "open", "priority": 4, "title": "Slow query"},
    ]

    print("--- filter only: status open AND priority > 3 ---")
    open_high = a2kit.projection.filter_records(issues, expr="status == 'open' && priority > 3")
    for r in open_high:
        print(r)

    print("\n--- fields only: id, title ---")
    titles = a2kit.projection.project_fields(issues, fields=["id", "title"])
    for r in titles:
        print(r)

    print("\n--- composed via format_response ---")
    env = a2kit.format_response(issues, filter="status == 'open'", fields=["id", "title"])
    print(f"format={env['format']}, truncated={env['truncated']}")
    print(env["data"])


if __name__ == "__main__":
    main()
