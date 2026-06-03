"""Public surface for ``a2kit.packages.log`` — THE author emission surface.

Lets tools import the discoverable surface as
``from a2kit.log import info, debug, warning, error``. Implementation lives in
``a2kit.packages.log`` to keep the canonical layout under ``packages/``.
"""

from __future__ import annotations

from a2kit.packages.log import debug, error, info, warning

__all__ = ["debug", "error", "info", "warning"]
