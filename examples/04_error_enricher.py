"""Error enrichment — turn cryptic API errors into actionable agent messages.

Real example: a SQL-wrapping MCP got `column "usr_id" does not exist`. The
agent has no schema; it can't fix the call. With an enricher chained behind
the tool decorator, the same exception becomes:

  Column not found: usr_id
  Available: user_id, email, created_at
  Did you mean: user_id?

The pattern: subclass the protocol-shaped `ErrorEnricher`, register it on a
`EnricherRegistry`, pass the registry as `enricher=` (or attach at the Router
level via `Router(..., enricher=...)`).

Enrichers compose — the registry tries each in order; first non-None wins.
Non-matching exceptions pass through untouched.

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


class ColumnSuggestionEnricher:
    """ErrorEnricher protocol: `.enrich(exc, *, tool_name) -> Exception`."""

    def __init__(self, available_columns: list[str]) -> None:
        self._available = available_columns

    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, ColumnNotFoundError):
            return exc
        suggestions = get_close_matches(exc.column, self._available, n=2, cutoff=0.5)
        msg = f"Column not found: {exc.column}\nAvailable: {', '.join(self._available)}"
        if suggestions:
            msg += f"\nDid you mean: {', '.join(suggestions)}?"
        if tool_name:
            msg += f"\n(while running tool {tool_name!r})"
        return RuntimeError(msg)


def main() -> None:
    columns = ["user_id", "email", "created_at"]
    registry = a2kit.EnricherRegistry()
    registry.register(ColumnSuggestionEnricher(columns))
    # Built-in: ConnectionNotFoundEnricher takes a ConnectionStore and adds a
    # "Available: ..." / "Did you mean: ..." suffix to ConnectionNotFound
    # errors. Wire it once at the Router level — every tool inherits.

    out = registry.enrich(ColumnNotFoundError("usr_id"), tool_name="execute_query")
    print(f"Enriched:\n{out}\n")

    # Compose at the tool decorator:
    @a2kit.tool(enricher=registry)
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
