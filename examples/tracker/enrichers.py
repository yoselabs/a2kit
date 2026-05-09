"""Error enrichers — turn raw exceptions into agent-actionable messages.

An enricher is a pure function ``(exc) -> str | None`` (or
``None`` to pass through). The framework wraps the tool, runs the
enricher on any exception, and re-raises with the enriched message
when the enricher returns a string. Routers attach enrichers via the
``enrichers`` class attribute (or the ``enrich(self, exc)`` method
when the enricher needs ``self``).
"""

from __future__ import annotations


def tracker_404_enricher(exc: Exception) -> str | None:
    """Rewrite ``KeyError`` / ``LookupError`` into a typed not-found message."""
    if isinstance(exc, (KeyError, LookupError)):
        target = str(exc).strip("'\"")
        return f"tracker: nothing found matching {target!r}. List first to discover valid ids."
    return None
