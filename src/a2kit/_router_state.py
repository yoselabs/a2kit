"""Thread-local for the active router during `RouterRegistry.apply()`.

# Auto-tag seam:
# `RouterRegistry.apply()` sets the active router + phase ('read'|'write')
# before invoking `router.register_read(server, store)` /
# `router.register_write(...)`. The fat `@a2kit.tool` decorator reads this
# state and merges the router's `name` (if `auto_tag`) and `capabilities`,
# plus `Cap.READ` or `Cap.WRITE` based on the phase.

Internal — never import from outside `a2kit`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.scaffold import Router


@dataclass
class _ActiveRouter:
    """Snapshot of router + phase active during a register_* call."""

    router: Router  # type: ignore[type-arg]
    phase: str  # "read" or "write"


_LOCAL = threading.local()


def _set_active(router: Router | None, phase: str | None) -> None:  # type: ignore[type-arg]
    """Internal seam used by `RouterRegistry.apply()` (and tests)."""
    if router is None or phase is None:
        _LOCAL.value = None
    else:
        _LOCAL.value = _ActiveRouter(router=router, phase=phase)


def _get_active() -> _ActiveRouter | None:
    """Return active router context, or None."""
    return getattr(_LOCAL, "value", None)


__all__ = ["_ActiveRouter", "_get_active", "_set_active"]
