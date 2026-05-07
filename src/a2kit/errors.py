"""Error enrichment — turn cryptic exceptions into agent-actionable ones.

An *enricher* is a function: it takes an exception and an optional tool name,
returns either the same exception (no change) or a new one with more context.
That's the entire contract — there is no Protocol, no Registry, no class
hierarchy. The decorator's `enricher=` kwarg accepts any callable that matches
the shape.

```python
def enrich_columns(exc: Exception, tool_name: str | None = None) -> Exception:
    if not isinstance(exc, ColumnNotFoundError):
        return exc
    return RuntimeError(f"Column not found: {exc.column}; available: …")
```

Compose multiple enrichers with `chain(*fns)` — runs each in order, returns
the first transformation. Authors with one enricher don't need it.

```python
@a2kit.tool(enricher=chain(enrich_columns, connection_enricher(store)))
async def query(...): ...
```

Built-in: `connection_enricher(store)` factory enriches `ConnectionNotFound`
with the saved-keys list and a difflib suggestion. Wraps the store; returns a
plain function — no class to subclass.
"""

from __future__ import annotations

from collections.abc import Callable
from difflib import get_close_matches
from typing import Any

from a2kit.exceptions import ConnectionNotFound

EnricherFn = Callable[[Exception, "str | None"], Exception]
"""Type alias: an enricher is `(exc, tool_name) -> exc`. Returning the same
object (`is exc`) means no enrichment was applied."""


def chain(*enrichers: EnricherFn) -> EnricherFn:
    """Compose enrichers — first one to transform wins, subsequent skip.

    Empty chain is the identity enricher.
    """

    def chained(exc: Exception, tool_name: str | None = None) -> Exception:
        for fn in enrichers:
            new = fn(exc, tool_name)
            if new is not exc:
                return new
        return exc

    return chained


def connection_enricher(store: Any) -> EnricherFn:
    """Enrich `ConnectionNotFound` with available-keys list + difflib suggestion.

    Other exceptions pass through. Replaces the v0.8
    `ConnectionNotFoundEnricher` class — closes over the store, no method
    dispatch.
    """

    def enrich(exc: Exception, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, ConnectionNotFound):
            return exc
        available = ["-".join(info.key) for info in store.list_connections()]
        wanted = "-".join(exc.key)
        parts = [f"Connection not found: {wanted}"]
        if available:
            parts.append(f"Available: {', '.join(sorted(available))}")
            close = get_close_matches(wanted, available, n=1, cutoff=0.5)
            if close:
                parts.append(f"Did you mean: {close[0]}?")
        else:
            parts.append("No connections are configured.")
        if tool_name is not None:
            parts.append(f"(while running tool {tool_name!r})")
        new = ConnectionNotFound(exc.key)
        new.args = ("\n".join(parts),)
        new.available_connections = available
        return new

    return enrich


__all__ = ["EnricherFn", "chain", "connection_enricher"]
