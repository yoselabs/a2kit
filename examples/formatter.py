"""Example: `a2kit.formatter` — TOON vs JSON heuristic + truncation.

Run: `uv run python examples/formatter.py`
"""

from __future__ import annotations

from a2kit import formatter


def main() -> None:
    rows = [
        {"id": "alpha", "color": "red"},
        {"id": "beta", "color": "blue"},
        {"id": "gamma", "color": "green"},
    ]
    print("uniform list -> TOON:")
    print(formatter.format_response(rows))

    single = {"id": "alpha", "color": "red", "blob": "x" * 4000}
    print("\nsingle dict + long string -> JSON, truncated:")
    print(formatter.format_response(single, truncate_at=20))

    print("\nbare truncate(...) on nested data:")
    print(formatter.truncate({"long": "y" * 100, "items": ["short", "z" * 100]}, max_chars=10))


if __name__ == "__main__":
    main()
