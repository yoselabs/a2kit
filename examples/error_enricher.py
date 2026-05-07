"""Example: custom ErrorEnricher subclass + EnricherRegistry chain.

Mirrors the pattern in a2db's column-not-found enrichment (`executor.py:47-74`).
A custom enricher detects "column not found" errors, fetches the table's actual
columns, and rewrites the exception with a `difflib` suggestion.

Run: `uv run python examples/error_enricher.py`
"""

from __future__ import annotations

from difflib import get_close_matches

import a2kit


class _ColumnNotFoundError(Exception):
    """Stand-in for a database driver's column-mismatch exception."""

    def __init__(self, column: str) -> None:
        self.column = column
        super().__init__(f"column not found: {column}")


class ColumnSuggestionEnricher:
    """Rewrites _ColumnNotFoundError into one that lists available columns."""

    def __init__(self, available_columns: list[str]) -> None:
        self._available = available_columns

    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, _ColumnNotFoundError):
            return exc
        suggestions = get_close_matches(exc.column, self._available, n=2, cutoff=0.5)
        msg = f"Column not found: {exc.column}\nAvailable: {', '.join(self._available)}"
        if suggestions:
            msg += f"\nDid you mean: {', '.join(suggestions)}?"
        if tool_name:
            msg += f"\n(while running tool {tool_name!r})"
        return _ColumnNotFoundError(exc.column).__class__(exc.column).__class__.__bases__[0](msg)


def main() -> None:
    columns = ["user_id", "email", "created_at"]
    registry = a2kit.EnricherRegistry()
    registry.register(ColumnSuggestionEnricher(columns))

    out = registry.enrich(_ColumnNotFoundError("usr_id"), tool_name="execute_query")
    print(f"Enriched: {out}")

    # Non-matching exceptions pass through untouched.
    raw = ValueError("something else")
    assert registry.enrich(raw) is raw
    print("Non-matching exception passed through unchanged.")


if __name__ == "__main__":
    main()
