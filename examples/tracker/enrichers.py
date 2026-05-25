"""Error enrichers — translate raw exceptions into typed AppError instances.

An enricher is a function ``(exc) -> AppError | None`` registered via the
router's ``@router.enricher`` decorator. The framework wraps the tool,
isinstance-dispatches the enricher on raised exceptions, and re-raises
the returned AppError when non-None. Returning None means the framework
falls through to the next enricher (router → app → defect quarantine).
"""

from __future__ import annotations

from a2effect import AppError


class TrackerNotFound(AppError):
    kind = "input"
    http_status = 404
    cli_exit_code = 2
    hint = "List first to discover valid ids."


def tracker_404_enricher(exc: LookupError) -> TrackerNotFound | None:
    """Rewrite ``KeyError`` / ``LookupError`` into a typed not-found AppError."""
    target = str(exc).strip("'\"")
    return TrackerNotFound(f"tracker: nothing found matching {target!r}.")
