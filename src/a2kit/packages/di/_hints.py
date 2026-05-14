"""Local copy of the resolve-hints fallback policy.

Vendored from ``a2kit.signature.resolve_hints`` so the DI package is
self-contained (no ``from a2kit.*`` imports outside ``a2kit.packages.di``).
Keeps the standalone-shipping gate green. See
``di-scoped-lifecycle`` design D9.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from typing import get_type_hints as _stdlib_get_type_hints

if TYPE_CHECKING:
    from collections.abc import Callable

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


def resolve_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    """Return type hints for ``fn``, or ``{}`` on any resolution failure.

    Logs a single WARN per ``__qualname__`` on failure so misannotated
    factories don't spam the log.
    """
    try:
        return _stdlib_get_type_hints(fn)
    except Exception as exc:
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE:
            _WARN_ONCE.add(name)
            _log.warning("resolve_hints failed for %s: %s", name, exc)
        return {}


__all__ = ["resolve_hints"]
