"""ErrorEnricher protocol + registry.

Generalises the pattern observed in both reference MCPs:

- A SQL-wrapping MCP's column-not-found enrichment — turns a "column X not
  found" backend error into a suggestion ("did you mean Y?") plus the available
  columns list.
- A Jira/Confluence-wrapping MCP's enricher cascade — handles JQL field
  suggestions, account-ID hints, read-only re-login hint, etc.

The shared shape: catch an exception, optionally rewrite it into a more
agent-helpful one (more context, suggestions, available alternatives), then return
either the same exception (no enrichment) or a new one of the appropriate subclass.

a2kit ships ONE built-in enricher (`ConnectionNotFoundEnricher`) because it follows
naturally from the existing `ConnectionStore` primitive. Domain-specific enrichers
(SQL columns, JQL fields, HTTP 4xx codes) belong in the consuming MCP, written as
subclasses of the `ErrorEnricher` protocol and added to a registry.
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from a2kit.exceptions import ConnectionNotFound

if TYPE_CHECKING:
    from a2kit.connections import ConnectionInfo, ConnectionStore


@runtime_checkable
class ErrorEnricher(Protocol):
    """Transform an exception into a more agent-helpful one.

    Implementations return either the original exception (no enrichment applied)
    or a new exception (typically of the same class, with extra attributes or a
    richer message).

    The `tool_name` keyword is provided as context — useful for hints like
    "Run: a2X login -c <name>" — but enrichers may ignore it.
    """

    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception: ...


class EnricherRegistry:
    """Run a chain of `ErrorEnricher`s in registration order.

    The first enricher that returns an exception **distinct** (by `is`) from the
    input wins; subsequent enrichers do not see the modified exception. This
    matches the natural intuition: each enricher is responsible for one error
    class, and once it fires, the chain is done.
    """

    def __init__(self) -> None:
        self._enrichers: list[ErrorEnricher] = []

    def register(self, enricher: ErrorEnricher) -> None:
        """Append an enricher to the chain."""
        self._enrichers.append(enricher)

    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        """Run the chain. Returns the first enriched exception, or `exc` unchanged."""
        for enricher in self._enrichers:
            new = enricher.enrich(exc, tool_name=tool_name)
            if new is not exc:
                return new
        return exc


class ConnectionNotFoundEnricher:
    """Built-in enricher — adds `available_connections` to `ConnectionNotFound` errors.

    Wraps a `ConnectionStore`. On `ConnectionNotFound`, fetches the list of saved
    connection keys, attaches them as an `available_connections` attribute, and
    rewrites the message to include them plus a `difflib`-based suggestion.

    Other exception classes pass through unchanged.
    """

    def __init__(self, store: ConnectionStore[ConnectionInfo]) -> None:
        self._store = store

    def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
        if not isinstance(exc, ConnectionNotFound):
            return exc
        available = ["-".join(info.key) for info in self._store.list_connections()]
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
        # Pydantic-frozen-friendly: ConnectionNotFound stores .key, message in args.
        new.args = ("\n".join(parts),)
        new.available_connections = available
        return new
