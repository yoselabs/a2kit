"""``app.log`` namespace — register custom handlers on the ``a2kit`` logger.

The built-in handlers are wired from config at app boot (see
``a2kit._log_bootstrap``); this is the seam for a consumer to attach its own
``logging.Handler`` (e.g. a structlog handler for a pretty dev console, per
ADR 0022) without reaching into the global logger directly.
"""

from __future__ import annotations

import logging

_LOGGER_NAME = "a2kit"


class _AppLog:
    """Namespace mounted on :class:`a2kit.App` as ``app.log``."""

    __slots__ = ()

    def add_handler(self, handler: logging.Handler) -> None:
        """Attach a custom handler to the ``a2kit`` logger."""
        logging.getLogger(_LOGGER_NAME).addHandler(handler)

    def remove_handler(self, handler: logging.Handler) -> None:
        """Remove a previously added handler from the ``a2kit`` logger."""
        logging.getLogger(_LOGGER_NAME).removeHandler(handler)

    @property
    def handlers(self) -> tuple[logging.Handler, ...]:
        """Immutable snapshot of the ``a2kit`` logger's current handlers."""
        return tuple(logging.getLogger(_LOGGER_NAME).handlers)


__all__ = ["_AppLog"]
