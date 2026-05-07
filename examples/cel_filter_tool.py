"""Example: `@a2kit.tool` with `cel_filter_param` + `fields_param` (v0.4).

Zero-boilerplate filter wiring: declare the kwargs as named function parameters,
let the decorator thread them into `format_response` automatically.

Run: `uv run python examples/cel_filter_tool.py`
"""

from __future__ import annotations

import a2kit

_WIDGETS = [
    {"id": 1, "name": "alpha", "color": "red", "stock": 3},
    {"id": 2, "name": "beta", "color": "blue", "stock": 0},
    {"id": 3, "name": "gamma", "color": "red", "stock": 7},
]


@a2kit.tool(cel_filter_param="filter", fields_param="fields")
def list_widgets(
    filter: str = "",  # noqa: A002
    fields: list[str] | None = None,
) -> list[dict]:
    """Return widgets, optionally filtered + projected by the agent."""
    return _WIDGETS


def main() -> None:
    print("--- raw call (no filter, no fields) ---")
    print(list_widgets())

    print("\n--- filter only ---")
    print(list_widgets(filter="color == 'red'"))

    print("\n--- filter + fields ---")
    print(list_widgets(filter="stock > 0", fields=["id", "name"]))


if __name__ == "__main__":
    main()
