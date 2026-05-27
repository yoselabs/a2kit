"""LDD wire formatting — the canonical ``[ +s.mmm LEVEL] msg key=val`` line.

This module re-exports the actual implementation from ``a2kit._ldd_wire``
(a foundational, layer-exempt module). The split exists so
``packages/context/`` can also route its CLI-stub emit through the same
primitives without forming an L0 cross-package cycle with ``packages/ldd/``
(see ``a2kit._ldd_wire`` docstring for the constraint).

Consumers SHOULD continue to import from this module — the indirection
is internal hygiene, not a deprecation.
"""

from __future__ import annotations

from a2kit._ldd_wire import TEXT_CAP, _cap_text, _format_kv, format_ldd_line

__all__ = ["TEXT_CAP", "_cap_text", "_format_kv", "format_ldd_line"]
