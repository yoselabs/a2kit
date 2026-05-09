"""Protocol-neutral exception enrichers.

An *enricher* is a function `(exc, tool_name) -> exc` that turns cryptic
errors into agent-actionable ones. Enrichers know nothing about MCP, CLI, or
fastmcp — they just transform exceptions. Adapters call `wrap(fn, enricher)`
before registering the tool so both protocols honor identical error semantics.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from difflib import get_close_matches
from typing import Any, TypeVar, cast

EnricherFn = Callable[[Exception, str], Exception]
"""`(exc, tool_name) -> enriched_exc`. Return same instance for passthrough."""

F = TypeVar("F", bound=Callable[..., Any])


def chain(*enrichers: EnricherFn) -> EnricherFn:
    """Compose enrichers left-to-right; first transformer wins, rest skip.

    Empty chain is the identity enricher.
    """

    def chained(exc: Exception, tool_name: str) -> Exception:
        current = exc
        for fn in enrichers:
            new = fn(current, tool_name)
            if new is not current:
                return new
        return current

    return chained


def wrap(fn: F, enricher: EnricherFn | None) -> F:
    """Wrap `fn` so any exception is funneled through `enricher`.

    Detects coroutine functions and returns the matching wrapper shape.
    `enricher=None` returns `fn` unchanged (zero overhead).
    """
    if enricher is None:
        return fn

    tool_name = getattr(fn, "__name__", "")

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                raise enricher(exc, tool_name) from exc

        return cast("F", async_wrapper)

    @functools.wraps(fn)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise enricher(exc, tool_name) from exc

    return cast("F", sync_wrapper)


def connection_enricher(store: Any) -> EnricherFn:
    """Enrich `ConnectionNotFound` with available-keys list + close-match hint.

    Other exceptions pass through. `store.list()` (sync) returns available
    connection keys. Imports `ConnectionNotFound` lazily to avoid a
    cross-package import at module load.
    """

    def enrich(exc: Exception, tool_name: str) -> Exception:
        from a2kit.packages.connections.exceptions import ConnectionNotFound

        if not isinstance(exc, ConnectionNotFound):
            return exc

        available: list[str] = list(store.list()) if hasattr(store, "list") else []
        wanted = "-".join(exc.key) if isinstance(exc.key, tuple) else str(exc.key)

        parts = [f"Connection not found: tried {wanted!r}"]
        if available:
            parts.append(f"available: {sorted(available)}")
            close = get_close_matches(wanted, available, n=1, cutoff=0.5)
            if close:
                parts.append(f"did you mean {close[0]!r}?")
        else:
            parts.append("no connections are configured.")
        if tool_name:
            parts.append(f"(while running tool {tool_name!r})")

        new = ConnectionNotFound(exc.key)
        new.args = ("; ".join(parts),)
        new.available_connections = available
        return new

    return enrich


__all__ = ["EnricherFn", "chain", "connection_enricher", "wrap"]
