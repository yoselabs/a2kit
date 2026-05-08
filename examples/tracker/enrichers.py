"""Error enrichers — turn raw exceptions into agent-actionable ones.

An enricher is just a function `(exc, tool_name) -> exc`. The tool decorator
calls it on the exception path so the message reaching the agent is precise:
agents can act on "task X not found in project Y" but waste turns on
"KeyError: 'X'".
"""

from __future__ import annotations


def tracker_404_enricher(exc: Exception, tool_name: str | None = None) -> Exception:
    """Rewrite `KeyError` / `LookupError` into a typed not-found message.

    The kit chains your enricher after `connection_enricher` (the default),
    so connection errors stay readable while domain errors get this layer.
    """
    if isinstance(exc, KeyError | LookupError):
        # KeyError stringifies its arg with surrounding quotes — strip them.
        target = str(exc).strip("'\"")
        msg = f"{tool_name or 'tracker'}: nothing found matching {target!r}. List first to discover valid ids."
        return LookupError(msg)
    return exc
