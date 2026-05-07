"""Error enrichment — turn cryptic API errors into actionable agent messages.

Real example: a SQL-wrapping MCP got `column "usr_id" does not exist`. The
agent has no schema; it can't fix the call. With an enricher attached to the
tool, the same exception becomes:

  Column not found: usr_id
  Available: user_id, email, created_at
  Did you mean: user_id?

An *enricher* is a function: `(exc, tool_name) -> exc`. Returning the same
object means no change; returning a new one replaces the raised exception.
That's the entire contract — no Protocol, no Registry, no class hierarchy.

Compose multiple enrichers with `chain(*fns)` (first transformer wins).

Run: `uv run python examples/04_error_enricher.py`
"""

from __future__ import annotations

from difflib import get_close_matches

import a2kit


class ColumnNotFoundError(Exception):
    """Driver-shaped exception — replace with whatever your client raises."""

    def __init__(self, column: str) -> None:
        self.column = column
        super().__init__(f"column not found: {column}")


def make_column_enricher(available: list[str]) -> a2kit.EnricherFn:
    """Closure factory — same shape as `a2kit.connection_enricher(store)`."""

    def enrich(exc: Exception, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, ColumnNotFoundError):
            return exc
        suggestions = get_close_matches(exc.column, available, n=2, cutoff=0.5)
        msg = f"Column not found: {exc.column}\nAvailable: {', '.join(available)}"
        if suggestions:
            msg += f"\nDid you mean: {', '.join(suggestions)}?"
        if tool_name:
            msg += f"\n(while running tool {tool_name!r})"
        return RuntimeError(msg)

    return enrich


def main() -> None:
    columns = ["user_id", "email", "created_at"]
    enrich_columns = make_column_enricher(columns)

    # Single enricher — call directly:
    out = enrich_columns(ColumnNotFoundError("usr_id"), "execute_query")
    print(f"Enriched:\n{out}\n")

    # Multiple enrichers — compose with chain(); first transformer wins.
    # `connection_enricher(store)` is the built-in factory; pass any store and
    # ConnectionNotFound exceptions get an "Available: …" / "Did you mean: …"
    # suffix automatically.
    @a2kit.tool(enricher=enrich_columns)
    def query(table: str, column: str) -> dict:
        if column not in columns:
            raise ColumnNotFoundError(column)
        return {"rows": []}

    try:
        query("users", "usr_id")
    except RuntimeError as exc:
        print(f"Tool raised:\n{exc}")


if __name__ == "__main__":
    main()
